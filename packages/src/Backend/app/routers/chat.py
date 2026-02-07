# from typing import Dict, Any, List, Optional
# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from datetime import datetime
# import uuid
# from .. import models, schemas, oauth2, database
# from . import orders

# from agents import agent_main


# router = APIRouter(
#     prefix="/chat",
#     tags=["chat"],
# )

# @router.post("/", response_model=Dict[str, Any])
# def chat_with_agent(chat_input: schemas.ChatInput, db: Session = Depends(database.get_db), current_user= Depends(oauth2.get_current_user)):
#     """
#     Process user input and interact with the agent system.
#     Handles both new messages and feedback on previous responses.
#     """
#     agent = agent_main.SuperAgent(current_user.id)
    
#     # Process the message through the agent
#     response = agent.process_message(chat_input.input_text)
    
#     # Save user message to database
#     chat_message = models.ChatMessage(
#         user_id=current_user.id, 
#         content=chat_input.input_text,
#         conversation_id=chat_input.conversation_id if hasattr(chat_input, 'conversation_id') else None
#     )
#     db.add(chat_message)
    
#     # If agent returned a response with text content, save it to the database
#     if response and "text_content" in response:
#         # Create AgentResponse with explicit parameter assignments
#         ai_message = models.AgentResponse(
#             type=response.get("type", "agent_response"),
#             text_content=response["text_content"],
#             structured_data=response.get("structured_data", {}),
#             timestamp=datetime.now(),
#             agent_type=response.get("agent_type", "unknown"),
#             requires_feedback=response.get("requires_feedback", False),
#             conversation_id=response.get("conversation_id", str(uuid.uuid4())),
#             conversation_ended=response.get("conversation_ended", False)
#         )
#         db.add(ai_message)
    
#     # Commit changes
#     db.commit()
#     db.refresh(chat_message)
    
#     return response
