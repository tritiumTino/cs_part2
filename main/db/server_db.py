from typing import List, Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

from main.variables import SERVER_DATABASE


class ServerDB:
    Base = declarative_base()

    class AllUsers(Base):
        __tablename__ = 'all_users'
        id = Column(Integer, primary_key=True)
        name = Column(String, unique=True, index=True)
        last_login = Column(DateTime)

        def __init__(self, name: str) -> None:
            self.name = name
            self.last_login = datetime.now()

    class ActiveUsers(Base):
        __tablename__ = 'active_users'
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey('all_users.id'), unique=True)
        ip_address = Column(String)
        port = Column(Integer)
        login_time = Column(DateTime)

        def __init__(self, user_id: int, ip_address: str, port: int, login_time: datetime) -> None:
            self.user_id = user_id
            self.ip_address = ip_address
            self.port = port
            self.login_time = login_time

    class LoginHistory(Base):
        __tablename__ = 'login_history'
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey('all_users.id'))
        ip_address = Column(String)
        port = Column(Integer)
        login_time = Column(DateTime)

        def __init__(self, user_id: int, ip_address: str, port: int, login_time: datetime) -> None:
            self.user_id = user_id
            self.ip_address = ip_address
            self.port = port
            self.login_time = login_time

    def __init__(self) -> None:
        self.database_engine = create_engine(SERVER_DATABASE, echo=False, pool_recycle=7200)
        self.Base.metadata.create_all(self.database_engine)

        Session = sessionmaker(bind=self.database_engine)
        self.session = Session()
        self.session.query(self.ActiveUsers).delete()
        self.session.commit()

    def user_login(self, username: str, ip_address: str, port: int) -> None:
        print(username, ip_address, port)

        result = self.session.query(self.AllUsers).filter_by(name=username)

        if result.count():
            user = result.first()
            user.last_login = datetime.now()
        else:
            user = self.AllUsers(name=username)
            self.session.add(user)
            self.session.commit()

        new_active_user = self.ActiveUsers(
            user_id=user.id,
            ip_address=ip_address,
            port=port,
            login_time=datetime.now()
        )
        self.session.add(new_active_user)

        history = self.LoginHistory(
            user_id=user.id,
            login_time=datetime.now(),
            ip_address=ip_address,
            port=port
        )
        self.session.add(history)
        self.session.commit()

    def user_logout(self, username: str) -> None:
        user = self.session.query(self.AllUsers).filter_by(name=username).first()
        self.session.query(self.ActiveUsers).filter_by(user_id=user.id).delete()
        self.session.commit()

    def users_list(self) -> List[tuple]:
        query = self.session.query(self.AllUsers.name, self.AllUsers.last_login)
        return query.all()

    def active_users_list(self) -> List[tuple]:
        query = self.session.query(
            self.AllUsers.name,
            self.ActiveUsers.ip_address,
            self.ActiveUsers.port,
            self.ActiveUsers.login_time
        ).join(self.AllUsers)
        return query.all()

    def login_history(self, username: Optional[str] = None) -> List[tuple]:
        query = self.session.query(
            self.AllUsers.name,
            self.LoginHistory.login_time,
            self.LoginHistory.ip_address,
            self.LoginHistory.port
        ).join(self.AllUsers)
        if username:
            query = query.filter(self.AllUsers.name == username)
        return query.all()
