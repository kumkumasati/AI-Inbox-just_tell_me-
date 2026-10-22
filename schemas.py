from typing import List, Optional
from pydantic import BaseModel, Field

class Message(BaseModel):
    id: int
    sender: str
    timestamp: str
    text: str

class ActionItem(BaseModel):
    task: str = Field(..., description="Actionable task")
    assignee: Optional[str] = Field(None, description="Person assigned or 'ME' if sender commits using 'I will...'")
    deadline: Optional[str] = Field(None, description="Deadline or target date/time mentioned")
    source_message_ids: List[int] = Field(..., description="List of message IDs backing this task")
    quote: str = Field(..., description="Exact quote of 3+ words copied from source messages")

class Decision(BaseModel):
    decision: str = Field(..., description="Decision or agreement reached")
    source_message_ids: List[int]
    quote: str

class Topic(BaseModel):
    title: str
    message_ids: List[int]

class Extraction(BaseModel):
    topics: List[Topic]
    action_items: List[ActionItem]
    decisions: List[Decision]

class Answer(BaseModel):
    answer: str
    source_message_ids: List[int]
    quote: str
