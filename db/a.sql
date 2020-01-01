create table tb_events (
  guild_id bigint not null,
  message_id bigint not null,
  data text not null,
  expiration_date timestamp without time zone not null,
  event_type smallint not null,
  primary key (guild_id, message_id)
);
