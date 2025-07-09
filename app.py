from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['SECRET_KEY'] = 'os.getenv('SECRET_KEY')'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

#userの定義
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    lines = db.relationship('Line', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

#lineの定義
class Line(db.Model):
    __tablename__ = 'line'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer,db.ForeignKey('user.id'), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    line_name =  db.Column(db.String(100), nullable=False)
    info_url = db.Column(db.String(255), nullable=True)
    memo = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    #デバック用
    def __repr__(self):
        return f'<line id={self.id} line_name={self.line_name}>'

def get_line_status(line_name, line_url):
    #汎用関数（状況と詳細を返す）

    '''
    if app.debug:
        print("--- 開発モード: ダミーデータを返します ---")

        return '横須賀線は平常運転です（開発用データ）', None

    '''
    
    try:
        response = requests.get(line_url, timeout=10)
        #HTTPステータスが200番台以外ならエラーを発生させる
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        #troubleクラスを持つdd要素を検索
        trouble_element = soup.find('dd', class_='trouble')

        if trouble_element:
            message = f'{line_name}は遅延しています'
            #ddタグ全体のテキストを取得する
            detail = trouble_element.get_text(strip=True)
            
            return message,detail

        else:
            message = f'{line_name}は通常運転です'
            #詳細情報がないのでNoneを返す
            return message,None

    except requests.exceptions.RequestException as e:
        message = f'{line_name}情報を取得できませんでした'
        detail = f'ネットワークエラーが発生しました:{e}'
        return message, detail
        
    except Exception as e:
        message = f'{line_name}情報を取得できませんでした'
        detail = f'予期せぬエラーが発生しました:{e}'
        return message, detail
    

#セッションからのIDを基にDBからユーザー情報を呼び出す
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

#index.htmlを表示するルート
@app.route('/')
def index():
    return render_template('index.html')

#会員登録処理
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return 'user already exists'

        new_user = User(username=username)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))
    
    return render_template('register.html')

#ログイン処理
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        #パスワードが正しいかチェック
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))

        return 'Invalid username or password'

    return render_template('login.html')

#ログアウト処理
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

#ログイン後の個人ダッシュボード,登録された路線をデバック
@app.route('/dashboard')
@login_required
def dashboard():
    my_lines= current_user.lines
    line_statuses = []

    for line in my_lines:
        #get_line_status関数を呼び出す
        status_message, status_detail = get_line_status(line.line_name, line.info_url)

        line_statuses.append({
            'id': line.id,  # 路線ごとの色分けに使うID
            'name': f"{line.company_name} {line.line_name}", # 会社名と路線名を結合
            'message': status_message,
            'detail': status_detail,
            'info_url': line.info_url
        })

    print("--登録路線デバック--")
    print(f"ユーザー名:{current_user.username}")

    #登録された路線がなければその旨を表示
    if not my_lines:
        print("-> このユーザーは路線未登録")
    else:
        for line in my_lines:
            print(
                f" -> ID: {line.id},"
                f"会社: {line.company_name}"
                f"路線: {line.line_name}"
            )

    print("-------------------------------")

    #JSTの現在時刻を取得
    jst = timezone(timedelta(hours=+9), 'JST')
    now = datetime.now(jst)
    #表示フォーマットを指定し文字列に変換
    update_time_str = now.strftime('%H:%M')

    return render_template('dashboard.html', username=current_user.username, statuses=line_statuses, update_time=update_time_str )

#路線選択フォームを表示するためのルート
@app.route('/dashboard/line-From', methods=['GET'])
@login_required
def show_add_line_form():
    return render_template('add_line_form.html')

#選択した線路を処理(DB保存)
@app.route('/dashboard/line-form', methods=['POST'])
@login_required
def add_my_line():
    #デバック(2行)
    print("--- add_my_line関数が呼び出されました ---")
    print(f"フォームから受け取ったデータ: {request.form.getlist('selected_lines')}")

    selected_lines_list = request.form.getlist('selected_lines')

    for line_string in selected_lines_list:
        try:
            #コロンで分割
            company, line_name, url= line_string.split('|')
        except ValueError:
            #形式が違うデータが来たらスキップ
            continue
        
        #ユーザーがその路線を登録済みかチェック
        existing_line = Line.query.filter_by(
            owner = current_user,
            company_name = company,
            line_name = line_name
        ).first()

        if not existing_line:
            new_line = Line(
                company_name=company,
                line_name=line_name,
                info_url = url,
                owner=current_user
            )
            db.session.add(new_line)

    db.session.commit()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username = 'testuser').first():
            test_user = User(username='testuser')
            test_user.set_password('password123')
            db.session.add(test_user)
            db.session.commit()
    app.run(debug=True)



