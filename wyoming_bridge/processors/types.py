from enum import Enum
from typing import Dict, List, NewType, TypedDict

ProcessorId = NewType('ProcessorId', str)
SubscriptionEventType = NewType('SubscriptionEventType', str)
ProcessorExtensions = Dict[str, str]

class SubscriptionStage(str, Enum):
    PRE_TARGET = "pre_target"
    POST_TARGET = "post_target"

class SubscriptionMode(str, Enum):
    BLOCKING = "blocking"
    NON_BLOCKING = "non_blocking"

class Subscription(TypedDict):
    event: SubscriptionEventType
    stage: SubscriptionStage
    mode: SubscriptionMode

class Processor(TypedDict):
    id: ProcessorId
    uri: str
    subscriptions: List[Subscription]

Processors = List[Processor]