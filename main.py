from dotenv import load_dotenv
load_dotenv()
import os
import logging
import asyncio
from decimal import Decimal
from web3 import Web3, HTTPProvider, Account
from zksync_sdk import ZkSyncProviderV01, HttpJsonRPCTransport, network, ZkSync, EthereumProvider, Wallet, ZkSyncSigner, EthereumSignerWeb3, ZkSyncLibrary
from zksync_sdk.types import ChangePubKeyEcdsa
from zksync_sdk.zksync_provider import FeeTxType
from db import DB


# Set logging
LOG_FORMAT="%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
# Load crypto library
library = ZkSyncLibrary()
# Create Zksync Provider
provider = ZkSyncProviderV01(provider=HttpJsonRPCTransport(network=network.mainnet))
# Setup web3
w3 = Web3(HTTPProvider(endpoint_uri="GETH_ENDPOINT"))


async def create_wallet_random_mnemonic():
    # Setup web3 account with random mnemonic
    Account.enable_unaudited_hdwallet_features()
    account, seed = Account.create_with_mnemonic()
    return seed, account.privateKey.hex(), account.address

async def create_wallet_from_key(prikey):
    # Setup web3 account #250
    account = Account.from_key(prikey)
    # Create EthereumSigner
    ethereum_signer = EthereumSignerWeb3(account=account)
    # Load contract address from server
    contracts = await provider.get_contract_address()
    # Setup zksync contract interactor
    zksync = ZkSync(account=account, web3=w3, zksync_contract_address=contracts.main_contract)
    # Create ethereum provider for interacting with ethereum node
    ethereum_provider = EthereumProvider(w3, zksync)
    # Initialize zksync signer, all creating options were described earlier
    signer = ZkSyncSigner.from_account(account, library, network.mainnet.chain_id)
    # Initialize Wallet
    wallet = Wallet(ethereum_provider=ethereum_provider, zk_signer=signer, eth_signer=ethereum_signer, provider=provider)
    return wallet

async def check_enough_balance(wallet, limit=0) -> bool:
    account_state = await wallet.get_account_state()
    committed_eth_balance = account_state.committed.balances.get("ETH")
    verified_eth_balance = account_state.verified.balances.get("ETH")
    if committed_eth_balance is None: committed_eth_balance = 0
    if verified_eth_balance is None: verified_eth_balance = 0
    logging.info("%s balance - committed %s - verified %s" % (wallet.address(),committed_eth_balance/1e18,verified_eth_balance/1e18))
    #balance = min(committed_eth_balance, verified_eth_balance)
    balance = committed_eth_balance
    if balance < limit:
        balance = balance/1e18
        logging.info("%s balance:%s" % (wallet.address(), balance))
        return False
    return True

async def wallet_is_empty(wallet) -> bool:
    account_state = await wallet.get_account_state()
    committed_eth_balance = account_state.committed.balances.get("ETH")
    verified_eth_balance = account_state.verified.balances.get("ETH")
    if committed_eth_balance is None: committed_eth_balance = 0
    if verified_eth_balance is None: verified_eth_balance = 0
    return committed_eth_balance == 0 and verified_eth_balance == 0

async def check_fee_is_low(wallet, rmb_fee_limit) -> bool:
    token = await wallet.resolve_token("ETH")
    active_fee = await wallet.zk_provider.get_transaction_fee(FeeTxType.change_pub_key_ecdsa,
            wallet.address(),"ETH")
    active_fee = active_fee.total_fee # int
    active_fee = active_fee/1e18
    eth_price = await wallet.zk_provider.get_token_price(token)
    eth_price = int(str(eth_price).split('.')[0])
    result = eth_price * 6.5 * active_fee < rmb_fee_limit
    if result:
        logging.info("%s * 6.5 * %s < %s" % (eth_price,active_fee,rmb_fee_limit))
    else:
        logging.info("%s * 6.5 * %s > %s" % (eth_price,active_fee,rmb_fee_limit))
    return result

async def wallet_is_active(wallet) -> bool:
    return await wallet.is_signing_key_set()

async def active_wallet(wallet) -> None:
    try:
        await wallet.set_signing_key("ETH", eth_auth_data=ChangePubKeyEcdsa())
    except Exception as e:
        logging.error("active failure: %s" % wallet.address())
        raise e

async def transfer(wallet, address, amount, token="ETH") -> None:
    try:
        tr = await wallet.transfer(address,amount=amount, token="ETH")
    except Exception as e:
        logging.error("transfer failure: %s" % e)
        raise e
    logging.info("%s transfer -> %s %s" % (wallet.address(), amount, address))

async def refund_eth_to_main_wallet(prikey, main_address, db) -> None:
    new_wallet = await create_wallet_from_key(prikey)
    balance = await new_wallet.get_balance("ETH", "committed")
    if balance > return_limit:
        return_amount = str((balance - return_limit)/1e18)
        amount = Decimal(return_amount)
        await transfer(new_wallet, main_address, amount)
        logging.info("%s from 2 -> 3" % new_wallet.address())
        db.update_prikey(prikey, "status", 3)


async def main(db, main_prikey, rmb_fee_limit, airdrop, new_wallet_balance, return_limit):
    # step 0: recover main wallet
    wallet = await create_wallet_from_key(main_prikey)
    # step 0.1 check mainnet address is active
    if not await wallet_is_active(wallet):
        await active_wallet(wallet)
    # step 0.2 prepare for next steps
    main_address = wallet.address()
    create_new_wallet = False
    logging.info("step 0: main wallet is actived - %s" % main_address)

    while True:
        # step 1: check main wallet status && current fee is low
        while True:
            # 1.1 enough eth balance
            if not await check_enough_balance(wallet, 0):
                logging.warning("step 1.1: not sufficient ETH, wait 10 seconds...")
                await asyncio.sleep(10)
                continue
            # 1.2 gas fee is low
            if not await check_fee_is_low(wallet, rmb_fee_limit):
                logging.warning("step 1.2: fee is too high, wait 30 seconds...")
                await asyncio.sleep(30)
                continue
            create_new_wallet = True
            break

        # step 2: search DB to deal
        if airdrop == "FALSE":
            # step 2.1 state 0: main wallet transfer 0.01 to it -> 1
            # step 2.1.1 get wallets with status 0 from DB
            addresses = db.get_addresses(0)
            # step 2.1.2 transfer 0.01 eth to every wallet in order
            logging.info("step 2.1: status 0 addresses: %s" % len(addresses))
            for address in addresses:
                # step 2.1.2.0 check main wallet balance
                if not await check_enough_balance(wallet, new_wallet_balance):
                    create_new_wallet = False
                    break
                # step 2.1.2.1 check new address balance
                address,prikey = address
                new_wallet = await create_wallet_from_key(prikey)
                if await check_enough_balance(new_wallet, new_wallet_balance):
                    logging.info("%s from 0 -> 1" % address)
                    db.update_address(address, "status", 1)
                    continue
                else:
                # step 2.1.2.2 transfer to it
                #if await wallet_is_empty(new_wallet):
                    amount=Decimal(str(new_wallet_balance/1e18))
                    await transfer(wallet, address, amount)
            # step 2.1.3 sleep 5 second
            if addresses: await asyncio.sleep(5)

            # step 2.2 state 1: recover new wallets then active -> 2
            # step 2.2.1 get private keys with status 1 from DB
            prikeys = db.get_prikeys(1)
            # step 2.2.2 recover new wallets then active
            logging.info("step 2.2: status 1 addresses: %s" % len(prikeys))
            for prikey in prikeys:
                # step 2.2.2.1 generate wallet object & check balance
                prikey = prikey[0]
                new_wallet = await create_wallet_from_key(prikey)
                # step 2.2.2.2 check active?
                if await wallet_is_active(new_wallet):
                    logging.info("%s from 1 -> 2" % new_wallet.address())
                    db.update_prikey(prikey, "status", 2)
                    continue
                await active_wallet(new_wallet)
            # step 2.2.3 sleep 5 second
            if prikeys: await asyncio.sleep(5)

            # step 2.3 state 2: recover new walletes check active and transfer 0.009 eth to main wallet -> 3
            # step 2.3.1 get private keys with status 2 from DB
            prikeys = db.get_prikeys(2)
            # step 2.3.2 recover new wallets then transfer
            logging.info("step 2.3: status 2 addresses: %s" % len(prikeys))
            await asyncio.gather(*[refund_eth_to_main_wallet(prikey[0], main_address, db) for prikey in prikeys])
            # step 2.3.4 show how many status 3 wallets
            logging.info("%s wallet finish receive active transfer" % db.count_status(3))

            # step 2.4 generate wallets to db with status 0
            if create_new_wallet:
                for i in range(5):
                    new_seed, new_prikey, new_address = await create_wallet_random_mnemonic()
                    db.insert_new_wallet(new_seed, new_prikey, new_address)
        else:
            pass
            # step 2.5 state 3: transfer zksync token to main wallet -> 4
            # step 2.6 state 4: transfer all eth to main wallet -> 5


if __name__ == "__main__":
    db = DB(logging)
    main_prikey = os.environ.get("MAIN_PRIKEY")
    rmb_fee_limit = 40
    airdrop = os.environ.get("AIRDROP")
    # 0.2e16 = 0.002
    #transfer_limit = 0.1e16
    new_wallet_balance = 0.3e16
    return_limit = 0.07e16
    try:
        asyncio.run(main(db, main_prikey, rmb_fee_limit, airdrop, new_wallet_balance, return_limit))
    except Exception as e:
        db.close()
        logging.error(e)
        raise
