import marshmallow
from marshmallow.fields import (
    List,
    Nested
)
from marshmallow_select import SchemaFilter
from marshmallow_sqlalchemy import ModelSchema
import pytest
import sqlalchemy as sa
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
)
from sqlalchemy.ext.declarative import (
    declared_attr,
    declarative_base
)
from sqlalchemy.orm import (
    relationship,
    sessionmaker
)

MARSHMALLOW_VERSION_INFO = tuple(
    [int(part) for part in marshmallow.__version__.split('.') if part.isdigit()]
)


def unpack(return_value):
    return return_value.data if MARSHMALLOW_VERSION_INFO[0] < 3 else return_value

query_counter = 0


def increment_qc(*args, **kwargs):
    global query_counter
    query_counter += 1


@pytest.fixture()
def Base():
    class MyBase(object):
        @declared_attr
        def __tablename__(cls):
            return cls.__name__.lower()
        id = Column(Integer, primary_key=True, nullable=False)
    return declarative_base(cls=MyBase)


@pytest.fixture()
def engine():
    return sa.create_engine('sqlite:///:memory:', echo=False)


@pytest.fixture()
def models(Base):
    class User(Base):
        first_name = Column(String(100))
        last_name = Column(String(100))
        email = Column(String(100))

        images = relationship('Image', back_populates='user')
        default_image = relationship('Image',
                                     uselist=False,
                                     primaryjoin=(
                                         "and_(User.id==Image.user_id, "
                                         "Image.is_default==True)"
                                     ))
        likes = relationship('Like', back_populates='user')

    class Image(Base):
        url = Column(String(100))
        is_default = Column(Boolean, default=False)

        user_id = Column(Integer, ForeignKey('user.id'))

        user = relationship('User', back_populates='images')

    class Like(Base):
        user_id = Column(Integer, ForeignKey('user.id'))
        image_id = Column(Integer, ForeignKey('image.id'))

        user = relationship('User', back_populates='likes')
        image = relationship('Image')

    class _models(object):
        def __init__(self):
            self.User = User
            self.Image = Image
            self.Like = Like
    return _models()


@pytest.fixture()
def shallow_schemas(models):
    class ShallowUserSchema(ModelSchema):
        class Meta:
            model = models.User

    class ShallowImageSchema(ModelSchema):
        class Meta:
            model = models.Image

    class ShallowLikeSchema(ModelSchema):
        class Meta:
            model = models.Like

    class _shallow_schemas(object):
        def __init__(self):
            self.ShallowUserSchema = ShallowUserSchema
            self.ShallowImageSchema = ShallowImageSchema
            self.ShallowLikeSchema = ShallowLikeSchema
    return _shallow_schemas()


@pytest.fixture()
def schemas(shallow_schemas):
    class UserSchema(shallow_schemas.ShallowUserSchema):
        images = List(Nested('ImageSchema'))
        likes = List(Nested('LikeSchema'))
        default_image = Nested('ImageSchema')

    class ImageSchema(shallow_schemas.ShallowImageSchema):
        user = Nested('UserSchema')
        users_who_like = List(Nested('UserSchema'))

    class LikeSchema(shallow_schemas.ShallowLikeSchema):
        user = Nested('UserSchema')
        image = Nested('ImageSchema')

    class _schemas(object):
        def __init__(self):
            self.UserSchema = UserSchema
            self.ImageSchema = ImageSchema
            self.LikeSchema = LikeSchema

    return _schemas()


@pytest.fixture()
def all_detail_schemas(schemas):
    class ImageForUserDetailSchema(schemas.ImageSchema):
        class Meta:
            fields = ['id', 'url']

    class LikeForUserDetailSchema(schemas.LikeSchema):
        image = Nested(ImageForUserDetailSchema)

        class Meta:
            fields = ['id', 'image']

    class UserDetailSchema(schemas.UserSchema):
        images = List(Nested(ImageForUserDetailSchema))
        likes = List(Nested(LikeForUserDetailSchema))

        class Meta:
            exclude = ['default_image']

    class _detail_schemas(object):
        def __init__(self):
            self.ImageForUserDetailSchema = ImageForUserDetailSchema
            self.LikeForUserDetailSchema = LikeForUserDetailSchema
            self.UserDetailSchema = UserDetailSchema

    return _detail_schemas()


@pytest.fixture()
def all_list_schemas(schemas):
    class ImageForUserListEltSchema(schemas.ImageSchema):
        class Meta:
            fields = ['id', 'url']

    class UserListEltSchema(schemas.UserSchema):
        default_image = Nested(ImageForUserListEltSchema)

        class Meta:
            fields = ['id', 'first_name', 'default_image']

    class _list_schemas(object):
        def __init__(self):
            self.ImageForUserListEltSchema = ImageForUserListEltSchema
            self.UserListEltSchema = UserListEltSchema

    return _list_schemas()


@pytest.fixture()
def detail_schema(all_detail_schemas):
    return all_detail_schemas.UserDetailSchema


@pytest.fixture()
def list_schema(all_list_schemas):
    return all_list_schemas.UserListEltSchema


@pytest.fixture()
def session(Base, models, engine):
    sa.event.listen(engine, 'before_cursor_execute', increment_qc)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_factory()


@pytest.fixture()
def instances(models, session):
    u = models.User(first_name='a', last_name='b', email='c')
    v = models.User(first_name='d', last_name='e', email='f')

    i0 = models.Image(user=u, url="goatse.cx/receiver.jpg", is_default=True)
    i1 = models.Image(user=v, url="goatse.cx/giver.jpg", is_default=True)
    i2 = models.Image(user=v, url="zombo.com/logo.png")

    r0 = models.Like(user=u, image=i1)
    r1 = models.Like(user=v, image=i0)

    users = [u, v]
    images = [i0, i1, i2]
    likes = [r0, r1]

    items = users + images + likes
    for obj in items:
        session.add(obj)

    session.flush()
    instance_data = {
        'user_id': u.id,
        'user0_img_id': i0.id,
        'user1_img_id': i1.id,
        'other_img_id': i2.id,
    }
    return instance_data


@pytest.fixture()
def detail_out():
    data = {
        'id': 1,
        'first_name': 'a',
        'last_name': 'b',
        'email': 'c',
        'images': [{'id': 1, 'url': 'goatse.cx/receiver.jpg'}],
        'likes': [{'id': 1, 'image': {'id': 2, 'url': 'goatse.cx/giver.jpg'}}]
    }
    return data


@pytest.fixture()
def list_out():
    data = [
        {
            'id': 1,
            'first_name': 'a',
            'default_image': {
                'url': 'goatse.cx/receiver.jpg',
                'id': 1
            }
        },
        {
            'id': 2,
            'first_name': 'd',
            'default_image': {
                'url': 'goatse.cx/giver.jpg',
                'id': 2
            }
        }
    ]

    return data


class TestJoining:
    def test_qc(self, session, models, instances):
        """
        qc ok
        """
        # TODO(dmr, 2017-05-31): probably possible to make
        # query_counter a fixture, rather than this ugly manual thing.
        # Ugly manual thing works tho.
        qc_before = query_counter

        num = session.query(models.User).count()

        qc_after = query_counter
        assert(num == 2)
        num_queries = qc_after - qc_before
        assert(num_queries == 1)

    def test_manual(self, session, detail_schema, detail_out, models, instances):
        """
        (TODO) this is what the next test is supposed to do

        sort of; it's not exaclty how i implemented the walk (maybe it
        should have been tho)
        """
        qc_before = query_counter

        qry = session.query(models.User).filter(models.User.id==instances['user_id'])

        qry = manually_project(qry)

        obj = qry.first()
        qc_fetch = query_counter
        data = unpack(detail_schema().dump(obj))
        qc_dump = query_counter
        assert data == detail_out, 'manual: data correct'

        fetch_queries = qc_fetch - qc_before
        dump_queries = qc_dump - qc_fetch
        assert fetch_queries == 1, 'manual: 1 to fetch'
        assert dump_queries == 0, 'manual: 0 to dump'

    def test_detail(self, session, detail_schema, detail_out, models, instances):
        """
        does it actually do it tho?
        """
        session.commit()
        qc_before = query_counter

        qry = session.query(models.User).filter(models.User.id==instances['user_id'])
        obj = qry.first()
        qc_fetch_unfiltered = query_counter
        data = unpack(detail_schema().dump(obj))
        qc_dump_unfiltered = query_counter

        assert data == detail_out, 'unfiltered gets data right'

        fetch_queries = qc_fetch_unfiltered - qc_before
        dump_queries = qc_dump_unfiltered - qc_fetch_unfiltered
        assert fetch_queries == 1, '1 query to fetch'
        assert dump_queries == 3, '3 queries to dump'

        session.commit()
        qc_before = query_counter

        qry = session.query(models.User).filter(models.User.id==instances['user_id'])
        sf = SchemaFilter(detail_schema(), unlazify=True)
        qry = sf(qry)
        obj = qry.first()
        qc_fetch_filtered = query_counter
        data = unpack(detail_schema().dump(obj))
        qc_dump_filtered = query_counter

        assert data == detail_out, 'filtered data correct'

        filt_fetch_queries = qc_fetch_filtered - qc_before
        filt_dump_queries = qc_dump_filtered - qc_fetch_filtered
        assert filt_fetch_queries == 1, 'filtered: 1 to fetch'
        assert filt_dump_queries == 0, 'filtered: 0 to dump'

    def test_list(self, session, list_schema, list_out, models, instances):
        session.commit()
        qc_before = query_counter

        qry = session.query(models.User)
        obj = qry.all()
        qc_fetch_unfiltered = query_counter
        data = unpack(list_schema(many=True).dump(obj))
        qc_dump_unfiltered = query_counter

        assert data == list_out, 'unfiltered gets data right'

        fetch_queries = qc_fetch_unfiltered - qc_before
        dump_queries = qc_dump_unfiltered - qc_fetch_unfiltered
        assert fetch_queries == 1, '1 query to fetch'
        assert dump_queries == 2, '2 queries to dump'

        session.commit()
        qc_before = query_counter

        qry = session.query(models.User)
        sf = SchemaFilter(list_schema(), unlazify=True)
        qry = sf(qry)
        obj = qry.all()
        qc_fetch_filtered = query_counter
        data = unpack(list_schema(many=True).dump(obj))
        qc_dump_filtered = query_counter

        assert data == list_out, 'filtered gets data right'

        fetch_queries = qc_fetch_filtered - qc_before
        dump_queries = qc_dump_filtered - qc_fetch_filtered
        assert fetch_queries == 1, 'filtered: 1 query to fetch'
        assert dump_queries == 0, 'filtered: 0 queries to dump'

        fetched_id_0 = instances['user0_img_id']
        fetched_id_1 = instances['user1_img_id']
        unfetched_id = instances['other_img_id']

        qc0 = query_counter
        session.query(models.Image).get(fetched_id_0).id
        qc1 = query_counter
        session.query(models.Image).get(fetched_id_1).id
        qc2 = query_counter
        session.query(models.Image).get(unfetched_id).id
        qc3 = query_counter

        assert (qc1 - qc0) == 0, 'already have user0 img'
        assert (qc2 - qc1) == 0, 'already have user0 img'
        assert (qc3 - qc2) == 1, 'did not get other img'


def manually_project(qry):
    from sqlalchemy.orm import (
        joinedload,
        noload,
        load_only,
    )

    qry = qry.options(noload('*'))

    qry = qry.options(joinedload('images'))
    qry = qry.options(joinedload('images').noload('*'))
    qry = qry.options(joinedload('images').load_only('id', 'url'))

    qry = qry.options(joinedload('likes'))
    qry = qry.options(joinedload('likes').noload('*'))

    qry = qry.options(joinedload('likes').joinedload('image'))
    qry = qry.options(joinedload('likes').joinedload('image').noload('*'))
    qry = qry.options(joinedload('likes').joinedload('image').load_only('id', 'url'))

    qry = qry.options(joinedload('likes').load_only('id'))

    qry = qry.options(load_only('id', 'first_name', 'last_name', 'email'))
    return qry
