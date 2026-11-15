from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,Text
from src.config.database import Base
class TraverseStudy(Base):
 __tablename__='traverse_studies'
 id:Mapped[int]=mapped_column(primary_key=True)
 name:Mapped[str]=mapped_column(String(150),unique=True)
 filename:Mapped[str]=mapped_column(String(180))
 description:Mapped[str]=mapped_column(Text,default='')
 # importing=分批导入未完成（不供计划/排队/修订）；ready=导入完成
 status:Mapped[str]=mapped_column(String(16),default='ready')
 expected_batches:Mapped[int]=mapped_column(default=0)
 received_batches:Mapped[int]=mapped_column(default=0)
 point_count:Mapped[int]=mapped_column(default=0)
