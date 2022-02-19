from typing import List, Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime


class ClientDB:
    Base = declarative_base()

    class KnownUsers(Base):
        __tablename__ = 'known_users'
        id = Column(Integer, primary_key=True)
        username = Column(String, unique=True, index=True)

        def __init__(self, name: str) -> None:
            self.username = name

    class Contacts(Base):
        __tablename__ = 'contacts'
        id = Column(Integer, primary_key=True)
        name = Column(String, unique=True)

        def __init__(self, contact: str) -> None:
            self.name = contact

    class MessageHistory(Base):
        __tablename__ = 'message_history'
        id = Column(Integer, primary_key=True)
        from_user = Column(String)
        to_user = Column(String)
        message = Column(Text)
        date = Column(DateTime)

        def __init__(self, from_user: str, to_user: str, message: str) -> None:
            self.from_user = from_user
            self.to_user = to_user
            self.message = message
            self.date = datetime.now()

    def __init__(self, name: str) -> None:
        self.database_engine = create_engine(
            f'sqlite:///client_{name}.db3',
            echo=False,
            pool_recycle=7200,
            connect_args={'check_same_thread': False}
        )

        self.Base.metadata.create_all(self.database_engine)

        Session = sessionmaker(bind=self.database_engine)
        self.session = Session()
        self.session.query(self.Contacts).delete()
        self.session.query(self.KnownUsers).delete()
        self.session.commit()

    def add_contact(self, contact: str) -> None:
        if not self.session.query(self.Contacts).filter_by(name=contact).count():
            contact_row = self.Contacts(contact)
            self.session.add(contact_row)
            self.session.commit()

    def del_contact(self, contact: str) -> None:
        self.session.query(self.Contacts).filter_by(name=contact).delete()
        self.session.commit()

    def add_users(self, users_list: List[str]) -> None:
        for user in users_list:
            user_row = self.KnownUsers(user)
            self.session.add(user_row)
        self.session.commit()

    def save_message(self, from_user: str, to_user: str, message: str) -> None:
        message_row = self.MessageHistory(from_user, to_user, message)
        self.session.add(message_row)
        self.session.commit()

    def get_contacts(self) -> Optional[List[str]]:
        return [contact[0] for contact in self.session.query(self.Contacts.name).all()]

    def get_users(self) -> Optional[List[str]]:
        return [user[0] for user in self.session.query(self.KnownUsers.username).all()]

    def check_user(self, user: str) -> bool:
        if self.session.query(self.KnownUsers).filter_by(username=user).count():
            return True
        return False

    def check_contact(self, contact: str) -> bool:
        if self.session.query(self.Contacts).filter_by(name=contact).count():
            return True
        return False

    def get_history(self, from_who: Optional[str] = None, to_who: Optional[str] = None) -> Optional[List[tuple]]:
        query = self.session.query(self.MessageHistory)
        if from_who:
            query = query.filter_by(from_user=from_who)
        if to_who:
            query = query.filter_by(to_user=to_who)
        return [(history_row.from_user, history_row.to_user, history_row.message, history_row.date)
                for history_row in query.all()]
