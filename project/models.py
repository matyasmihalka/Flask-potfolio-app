from project import database, bcrypt
from flask import current_app
from datetime import datetime, timedelta
import requests


class Stock(database.Model):
    """
    Class that represents a purchased stock in a portfolio

    The following attributes of a stock are stored in this table:
        stock symbol (type: string)
        number of shares (type: integer)
        purchase price (type: integer)
        primary key of User that owns the stock (type: integer)
        purchase date (type: datetime)
        current price (type: integer)
        date when current price was retrieved from the Alpha Vantage API (type: datetime)
        position value = current price * number of shares (type: integer)

    Note: Due to a limitation in the data types supported by SQLite, the
          purchase price, current price, and position value are stored as integers:
              $24.10 -> 2410
              $100.00 -> 10000
              $87.65 -> 8765
    """

    __tablename__ = 'stocks'

    id = database.Column(database.Integer, primary_key=True)
    stock_symbol = database.Column(database.String, nullable=False)
    number_of_shares = database.Column(database.Integer, nullable=False)
    purchase_price = database.Column(database.Integer, nullable=False)
    user_id = database.Column(database.Integer, database.ForeignKey('users.id'))
    purchase_date = database.Column(database.DateTime)
    current_price = database.Column(database.Integer)
    current_price_date = database.Column(database.DateTime)
    position_value = database.Column(database.Integer)

    def __init__(self, stock_symbol: str, number_of_shares: str, purchase_price: str,
                 user_id: int, purchase_date=None):
        self.stock_symbol = stock_symbol
        self.number_of_shares = int(number_of_shares)
        self.purchase_price = int(float(purchase_price) * 100)
        self.user_id = user_id
        self.purchase_date = purchase_date
        self.current_price = 0
        self.current_price_date = None
        self.position_value = 0

    def create_alpha_vantage_get_url_daily_compact(self):
        return 'https://www.alphavantage.co/query?function={}&symbol={}&outputsize={}&apikey={}'.format(
            'TIME_SERIES_DAILY_ADJUSTED',
            self.stock_symbol,
            'compact',
            current_app.config['ALPHA_VANTAGE_API_KEY']
    )

    def get_stock_data(self):
        if self.current_price_date is None or self.current_price_date.date() != datetime.now().date():
            url = self.create_alpha_vantage_get_url_daily_compact()

            try:
                r = requests.get(url)
            except requests.exceptions.ConnectionError:
                current_app.logger.error(f'Error! Network problem preventing retrieving the stock data ({ self.stock_symbol })!')

            # Status code returned from Alpha Vantage needs to be 200 (OK) to process stock data
            if r.status_code != 200:
                current_app.logger.warning(f'Error! Received unexpected status code ({ r.status_code }) '
                                        f'when retrieving stock data ({ self.stock_symbol })!')
                return

            daily_data = r.json()

            # The key of 'Time Series (Daily)' needs to be present in order to process the stock data
            # Typically, this key will not be present if the API rate limit has been exceeded.
            if 'Time Series (Daily)' not in daily_data:
                current_app.logger.warning(f'Could not find Time Series (Daily) key when retrieving '
                                        f'the stock data ({ self.stock_symbol })!')
                return

            for element in daily_data['Time Series (Daily)']:
                current_price = float(daily_data['Time Series (Daily)'][element]['4. close'])
                self.current_price = int(float(current_price) * 100)
                self.current_price_date = datetime.now()
                self.position_value = self.current_price * self.number_of_shares
                break
            current_app.logger.debug(f'Retrieved current price {self.current_price / 100} '
                                    f'for the stock data ({ self.stock_symbol })!')

    def get_stock_position_value(self) -> float:
        return float(self.position_value / 100)

    def create_alpha_vantage_get_url_weekly(self):
        return 'https://www.alphavantage.co/query?function={}&symbol={}&apikey={}'.format(
            'TIME_SERIES_WEEKLY_ADJUSTED',
            self.stock_symbol,
            current_app.config['ALPHA_VANTAGE_API_KEY']
        )

    def get_weekly_stock_data(self):
        title = ''
        labels = []
        values = []
        url = self.create_alpha_vantage_get_url_weekly()

        try:
            r = requests.get(url)
        except requests.exceptions.ConnectionError:
            current_app.logger.info(
                f'Error! Network problem preventing retrieving the weekly stock data ({self.stock_symbol})!')

        # Status code returned from Alpha Vantage needs to be 200 (OK) to process stock data
        if r.status_code != 200:
            current_app.logger.warning(f'Error! Received unexpected status code ({r.status_code}) '
                                    f'when retrieving weekly stock data ({self.stock_symbol})!')
            return '', '', ''

        weekly_data = r.json()

        # The key of 'Weekly Adjusted Time Series' needs to be present in order to process the stock data
        # Typically, this key will not be present if the API rate limit has been exceeded.
        if 'Weekly Adjusted Time Series' not in weekly_data:
            current_app.logger.warning(f'Could not find the Weekly Adjusted Time Series key when retrieving '
                                    f'the weekly stock data ({self.stock_symbol})!')
            return '', '', ''

        title = f'Weekly Prices ({self.stock_symbol})'

        # Determine the start date as either:
        #   - If the start date is less than 12 weeks ago, then use the date from 12 weeks ago
        #   - Otherwise, use the purchase date
        start_date = self.purchase_date
        if (datetime.now() - self.purchase_date) < timedelta(weeks=12):
            start_date = datetime.now() - timedelta(weeks=12)

        for element in weekly_data['Weekly Adjusted Time Series']:
            date = datetime.fromisoformat(element)
            if date.date() > start_date.date():
                labels.append(date)
                values.append(weekly_data['Weekly Adjusted Time Series'][element]['4. close'])

        # Reverse the elements as the data from Alpha Vantage is read in latest to oldest
        labels.reverse()
        values.reverse()

        return title, labels, values


class User(database.Model):
    """
    Class that represents a user of the application

    The following attributes of a user are stored in this table:
        * email - email address of the user
        * hashed password - hashed password (using Flask-Bcrypt)
        * registered_on - date & time that the user registered
        * email_confirmation_sent_on - date & time that the confirmation email was sent
        * email_confirmed - flag indicating if the user's email address has been confirmed
        * email_confirmed_on - date & time that the user's email address was confirmed

    REMEMBER: Never store the plaintext password in a database!
    """
    __tablename__ = 'users'

    id = database.Column(database.Integer, primary_key=True)
    email = database.Column(database.String, unique=True)
    password_hashed = database.Column(database.String(60))
    registered_on = database.Column(database.DateTime)                  
    email_confirmation_sent_on = database.Column(database.DateTime)     
    email_confirmed = database.Column(database.Boolean, default=False)  
    email_confirmed_on = database.Column(database.DateTime)
    stocks = database.relationship('Stock', backref='user', lazy='dynamic')

    def __init__(self, email: str, password_plaintext: str):
        self.email = email
        self.password_hashed = self.password_hashed = self._generate_password_hash(password_plaintext)
        self.registered_on = datetime.now()
        self.email_confirmation_sent_on = datetime.now()
        self.email_confirmed = False
        self.email_confirmed_on = None

    def is_password_correct(self, password_plaintext: str):
        return bcrypt.check_password_hash(self.password_hashed, password_plaintext)

    def __repr__(self):
        return f'<User: {self.email}>'

    @property
    def is_authenticated(self):  # NEW!!
        """Return True if the user has been successfully registered."""
        return True

    @property
    def is_active(self):  # NEW!!
        """Always True, as all users are active."""
        return True

    @property
    def is_anonymous(self):  # NEW!!
        """Always False, as anonymous users aren't supported."""
        return False

    def get_id(self):  # NEW!!
        """Return the user ID as a unicode string (`str`)."""
        return str(self.id)

    def set_password(self, password_plaintext: str):
        self.password_hashed = self._generate_password_hash(password_plaintext)

    @staticmethod
    def _generate_password_hash(password_plaintext):
        return bcrypt.generate_password_hash(
            password_plaintext,
            current_app.config.get('BCRYPT_LOG_ROUNDS')
        ).decode('utf-8')