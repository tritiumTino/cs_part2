from typing import List, Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime


class ServerDB:
    Base = declarative_base()

    class AllUsers(Base):
        __tablename__ = 'Users'
        id = Column(Integer, primary_key=True)
        name = Column(String, unique=True, index=True)
        last_login = Column(DateTime)

        def __init__(self, name: str) -> None:
            self.name = name
            self.last_login = datetime.now()

    class ActiveUsers(Base):
        __tablename__ = 'Active Users'
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey('Users.id'), unique=True)
        ip_address = Column(String)
        port = Column(Integer)
        login_time = Column(DateTime)

        def __init__(self, user_id: int, ip_address: str, port: int, login_time: datetime) -> None:
            self.user_id = user_id
            self.ip_address = ip_address
            self.port = port
            self.login_time = login_time

    class LoginHistory(Base):
        __tablename__ = 'Login History'
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey('Users.id'))
        ip_address = Column(String)
        port = Column(Integer)
        login_time = Column(DateTime)

        def __init__(self, user_id: int, ip_address: str, port: int, login_time: datetime) -> None:
            self.user_id = user_id
            self.ip_address = ip_address
            self.port = port
            self.login_time = login_time

    class Contacts(Base):
        __tablename__ = 'Contacts'
        id = Column(Integer, primary_key=True)
        user_id = Column(ForeignKey('Users.id'))
        contact_id = Column(ForeignKey('Users.id'))

        def __init__(self, user_id: int, contact_id: int) -> None:
            self.user_id = user_id
            self.contact_id = contact_id

    class History(Base):
        __tablename__ = "History"
        id = Column(Integer, primary_key=True)
        user_id = Column(ForeignKey('Users.id'))
        sent = Column(Integer)
        accepted = Column(Integer)

        def __init__(self, user_id: int) -> None:
            self.user_id = user_id
            self.sent = 0
            self.accepted = 0

    def __init__(self, path) -> None:
        self.database_engine = create_engine(
            f'sqlite:///{path}',
            echo=False,
            pool_recycle=7200,
            connect_args={'check_same_thread': False}
        )
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
            user_history = self.History(user.id)
            self.session.add(user_history)

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

    def process_message(self, sender_name: str, recipient_name: str) -> None:
        sender_id = self.session.query(self.AllUsers).filter_by(name=sender_name).first().id
        recipient_id = self.session.query(self.AllUsers).filter_by(name=recipient_name).first().id

        sender_row = self.session.query(self.History).filter_by(user_id=sender_id).first()
        sender_row.sent += 1
        recipient_row = self.session.query(self.History).filter_by(user_id=recipient_id).first()
        recipient_row.accepted += 1

        self.session.commit()

    def add_contact(self, user_name: str, contact_name: str) -> None:
        user = self.session.query(self.AllUsers).filter_by(name=user_name).first()
        contact = self.session.query(self.AllUsers).filter_by(name=contact_name).first()

        if not contact or self.session.query(self.Contacts).filter_by(
                user_id=user.id,
                contact_id=contact.id
        ).count():
            return

        contact_row = self.Contacts(user.id, contact.id)
        self.session.add(contact_row)
        self.session.commit()

    def remove_contact(self, user_name: str, contact_name: str) -> None:
        user = self.session.query(self.AllUsers).filter_by(name=user_name).first()
        contact = self.session.query(self.AllUsers).filter_by(name=contact_name).first()

        if not contact:
            return

        self.session.query(self.Contacts).filter(
            self.Contacts.user_id == user.id,
            self.Contacts.contact_id == contact.id
        ).delete()
        self.session.commit()

    def get_contacts(self, user_name: str) -> Optional[List[str]]:
        user = self.session.query(self.AllUsers).filter_by(name=user_name).one()

        query = self.session.query(
            self.Contacts,
            self.AllUsers.name
        ).filter_by(user_id=user.id).join(self.AllUsers, self.Contacts.contact_id == self.AllUsers.id)

        return [contact[1] for contact in query.all()]

    def message_history(self) -> Optional[List[tuple]]:
        query = self.session.query(
            self.AllUsers.name,
            self.AllUsers.last_login,
            self.History.sent,
            self.History.accepted
        ).join(self.AllUsers)
        return query.all()
