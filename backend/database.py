from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# مكان قاعدة البيانات: ملف اسمه tabayyun.db في نفس المجلد
engine = create_engine("sqlite:///./tabayyun.db")

# Session = "جلسة" نكلّم فيها قاعدة البيانات
SessionLocal = sessionmaker(bind=engine)


# كل الجداول بترث من هذا الكلاس
class Base(DeclarativeBase):
    pass