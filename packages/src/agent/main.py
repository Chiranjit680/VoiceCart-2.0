from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.messages import BaseMessage, HumanMessage
from agent_main import AgentExecutor
import uvicorn
app = FastAPI()

class AgentRequest(BaseModel):
    msg: str

@app.post("/agent/{user_id}")
async def agent_endpoint(user_id: int, body: AgentRequest):
    try:            
        response =  AgentExecutor().invoke(body.msg)
        return {"response": response}
    except Exception as e:
        print(f"Error processing agent request for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    
        
        
if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8002)
        
    #8002 for Agent microservice