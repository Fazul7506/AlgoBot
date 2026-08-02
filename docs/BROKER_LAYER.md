# Broker Layer

AlgoBot routes trading operations through `apps.broker.interfaces.BrokerInterface`, `BrokerService`, and broker adapters. Business logic must call broker-neutral methods (`buy`, `sell`, `balance`, `history`, `positions`, `orders`, `subscribe_ticks`) rather than vendor SDKs.
