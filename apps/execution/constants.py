ORDER_STATUS_DRAFT='draft'; ORDER_STATUS_VALIDATED='validated'; ORDER_STATUS_QUEUED='queued'; ORDER_STATUS_SENT='sent_to_broker'; ORDER_STATUS_ACCEPTED='accepted'; ORDER_STATUS_EXECUTED='executed'; ORDER_STATUS_ARCHIVED='archived'; ORDER_STATUS_FAILED='failed'; ORDER_STATUS_CANCELLED='cancelled'
POSITION_STATUS_OPEN='open'; POSITION_STATUS_CLOSED='closed'
CONTRACT_STATUS_PROPOSED='proposed'; CONTRACT_STATUS_PURCHASED='purchased'; CONTRACT_STATUS_EXPIRED='expired'; CONTRACT_STATUS_SOLD='sold'
QUEUE_STATUS_PENDING='pending'; QUEUE_STATUS_PROCESSING='processing'; QUEUE_STATUS_RETRY='retry'; QUEUE_STATUS_DONE='done'; QUEUE_STATUS_FAILED='failed'; QUEUE_STATUS_CANCELLED='cancelled'
ORDER_TYPES=['market','limit','stop','stop_limit','take_profit','stop_loss','trailing_stop']
DIRECTIONS=['buy','sell']
DERIV_CONTRACT_TYPES=['rise_fall','higher_lower','touch_no_touch','in_out','ends_between','stays_between','matches_differs','even_odd','over_under','accumulators','multipliers','vanilla_options','lookbacks','turbos']
RETRYABLE_ERRORS={'network_failure','timeout','temporary_broker_error'}
NON_RETRYABLE_ERRORS={'invalid_order','authentication_failure','validation_failure'}
WS_EVENTS=['OrderCreated','OrderValidated','OrderQueued','OrderExecuted','PositionOpened','PositionUpdated','PositionClosed','ContractPurchased','ContractExpired','ExecutionFailed']
