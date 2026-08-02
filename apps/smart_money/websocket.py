import logging
logger=logging.getLogger(__name__)
EVENTS=['BOSDetected','CHoCHDetected','MSSDetected','OrderBlockCreated','OrderBlockMitigated','BreakerDetected','FVGCreated','FVGFilled','LiquiditySweepDetected','InstitutionalBiasChanged','ConfluenceUpdated','NarrativeUpdated']
def broadcast_smc_event(event, payload):
    if event not in EVENTS: raise ValueError(f'Unsupported SMC event: {event}')
    logger.info('SMC websocket event %s: %s', event, payload); return {'event':event,'payload':payload}
