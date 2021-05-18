CREATE TABLE IF NOT EXISTS wallets (
	id integer primary key,
	seed varchar(120) not null,
	prikey char(66) not null,
	address char(42) not null,
	status smallint default 0,
	unique (prikey,address));
CREATE INDEX IF NOT EXISTS wallet_status ON wallets (status);
