from database import Base, SessionLocal, engine
from models import Classification, Role

# ١. ابنِ الجداول (إذا مو موجودة)
Base.metadata.create_all(engine)

# ٢. عبّي البيانات
with SessionLocal() as db:
    if db.query(Role).count() > 0:
        print("البيانات موجودة من قبل")
    else:
        db.add_all([
            Role(code="new_employee", name_ar="موظف جديد"),
            Role(code="service_employee", name_ar="موظف خدمة"),
            Role(code="supervisor", name_ar="مشرف", approval_level=3),
            Role(code="manager", name_ar="مدير", approval_level=4),
            Role(code="admin", name_ar="مدير النظام"),

            Classification(code="public", name_ar="عام", level=1),
            Classification(code="restricted", name_ar="مقيّد", level=2),
            Classification(code="secret", name_ar="سري", level=3),
            Classification(code="top_secret", name_ar="سري للغاية", level=4),
        ])
        db.commit()
        print("تمت التعبئة ✅")
        