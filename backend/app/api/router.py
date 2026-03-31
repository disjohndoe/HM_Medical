from fastapi import APIRouter

from app.api.appointments import router as appointments_router
from app.api.auth import router as auth_router
from app.api.cezih import router as cezih_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.medical_records import router as medical_records_router
from app.api.patients import router as patients_router
from app.api.plan import router as plan_router
from app.api.prescriptions import router as prescriptions_router
from app.api.procedures import router as procedures_router
from app.api.settings import router as settings_router
from app.api.users import router as users_router

api_router = APIRouter()
api_router.include_router(appointments_router)
api_router.include_router(auth_router)
api_router.include_router(cezih_router)
api_router.include_router(dashboard_router)
api_router.include_router(documents_router)
api_router.include_router(medical_records_router)
api_router.include_router(patients_router)
api_router.include_router(plan_router)
api_router.include_router(prescriptions_router)
api_router.include_router(procedures_router)
api_router.include_router(settings_router)
api_router.include_router(users_router)
