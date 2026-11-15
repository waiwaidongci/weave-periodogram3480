from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,String,Integer,DateTime,UniqueConstraint
from datetime import datetime,timezone
from src.config.database import Base
class ImportBatch(Base):
 __tablename__='import_batches'
 __table_args__=(UniqueConstraint('study_id','batch_index'),)
 id:Mapped[int]=mapped_column(primary_key=True)
 study_id:Mapped[int]=mapped_column(ForeignKey('traverse_studies.id'))
 batch_index:Mapped[int]=mapped_column(Integer)
 point_count:Mapped[int]=mapped_column(Integer)
 created_by:Mapped[str]=mapped_column(String(120))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
