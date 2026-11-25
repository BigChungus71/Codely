# Static fullstack demo fixture only. Never import or execute.
import os
from fastapi import FastAPI
from .routes import router

app = FastAPI(debug=False)
app.include_router(router)
ENV_NAME = os.getenv('APP_ENV', 'dev')
