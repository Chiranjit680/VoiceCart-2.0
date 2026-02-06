from fastapi import FastAPI, HTTPException
from langchain_core.messages import BaseMessage, HumanMessage
from agent_main import AgentExecutor
import uvicorn
app = FastAPI()

@app.post("/agent/{user_id}")
async def agent_endpoint(msg: str):
    try:            
        response = await AgentExecutor().invoke(msg)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
        
if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8067)
        
    