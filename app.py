from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

from werkzeug.security import generate_password_hash, check_password_hash
import random
import pandas as pd
import os
import re


app = Flask(__name__)
# 基础配置
#app.config['SECRET_KEY'] = 'dian_gong_kao_shi_2026'
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or '请在生产环境设置FLASK_SECRET_KEY环境变量'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'electrical_exam.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# ---------------------- 数据库表定义 ----------------------
# 用户表
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(10), default='student')  # admin/student


# 电工题库表
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    q_type = db.Column(db.String(10), nullable=False)  # 单选/判断/多选
    content = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200))
    option_b = db.Column(db.String(200))
    option_c = db.Column(db.String(200))
    option_d = db.Column(db.String(200))
    answer = db.Column(db.String(10), nullable=False)
    explain = db.Column(db.Text)


# 考试成绩表
class ExamRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    create_time = db.Column(db.DateTime, default=db.func.now())


# 错题本表
class WrongQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    wrong_answer = db.Column(db.String(10))  # 用户选错的答案
    wrong_count = db.Column(db.Integer, default=1)  # 错误次数
    last_wrong_time = db.Column(db.DateTime, default=db.func.now())
    __table_args__ = (db.UniqueConstraint('user_id', 'question_id', name='uq_user_question'),)

# 收藏表
class FavoriteQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    create_time = db.Column(db.DateTime, default=db.func.now())
    __table_args__ = (db.UniqueConstraint('user_id', 'question_id', name='uq_fav_user_question'),)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------- 路由接口 ----------------------
# 首页
@app.route('/')
def index():
    return render_template('index.html', user=current_user)


# 登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('账号或密码错误')
    return render_template('login.html')


# 退出
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录')
    return redirect(url_for('login'))


# 随机刷题页面
@app.route('/practice')
@login_required
def practice():
    all_questions = Question.query.all()
    #random.shuffle(all_questions)
    fav_ids = set(
        f.question_id
        for f in FavoriteQuestion.query.filter_by(user_id=current_user.id).all()
    )
    return render_template('practice.html', questions=all_questions, fav_ids=fav_ids)


# 模拟考试：自动抽100道题（30单选+70判断）
@app.route('/exam', methods=['GET', 'POST'])
@login_required
def exam():
    if request.method == 'POST':
        right_count = 0
        answered = 0

        for qid in request.form.keys():
            try:
                qid_int = int(qid)
            except:
                continue

            q = Question.query.get(qid_int)
            if not q:
                continue

            is_correct = False

            """
             if q.q_type == '多选':
                user_vals = request.form.getlist(qid)
                user_ans_sorted = ''.join(sorted([v.upper() for v in user_vals]))
                correct_ans_sorted = ''.join(sorted(q.answer.upper()))
                answered += 1
                if user_ans_sorted == correct_ans_sorted:
                    right_count += 1
                    is_correct = True
            else:
            """
            user_ans = request.form.get(qid, '').upper()
            answered += 1
            if q.answer.upper() == user_ans:
                right_count += 1
                is_correct = True

            # 记录错题
            if not is_correct:
                wrong = WrongQuestion.query.filter_by(
                    user_id=current_user.id,
                    question_id=q.id
                ).first()
                if wrong:
                    wrong.wrong_count += 1
                    wrong.wrong_answer = user_ans  # 更新最近一次错误答案
                    wrong.last_wrong_time = db.func.now()
                else:
                    db.session.add(WrongQuestion(
                        user_id=current_user.id,
                        question_id=q.id,
                        wrong_answer=user_ans,
                        wrong_count=1
                    ))

        score = int((right_count / answered) * 100) if answered > 0 else 0
        db.session.commit()
        record = ExamRecord(user_id=current_user.id, score=score)
        db.session.add(record)
        db.session.commit()
        return f"<h2>考试完成，您的得分：{score}分，80分及格</h2><p><a href='/'>返回首页</a></p>"

    # GET请求：随机组卷
    single_pool = Question.query.filter_by(q_type='单选').all()
    judge_pool = Question.query.filter_by(q_type='判断').all()
    #multi_pool = Question.query.filter_by(q_type='多选').all()

    single = random.sample(single_pool, min(30, len(single_pool)))
    judge = random.sample(judge_pool, min(70, len(judge_pool)))
    #multi = random.sample(multi_pool, min(20, len(multi_pool)))

    #exam_paper = single + judge + multi
    exam_paper = judge + single
    #random.shuffle(exam_paper)
    return render_template('exam.html', paper=exam_paper)


# 管理员：Excel批量导入题库
@app.route('/admin/import', methods=['GET', 'POST'])
@login_required
def import_question():
    if current_user.role != 'admin':
        return '无权限'

    if request.method == 'POST':
        file = request.files['file']

        # 建议指定 engine 和 dtype=str，避免数字/布尔/NaN问题
        df = pd.read_excel(file, engine='openpyxl', dtype=str)

        # 清洗列名：去掉空格、换行、制表符、零宽空格、BOM等
        df.columns = [re.sub(r"[\s\u200b\u200c\u200d\uFEFF\r\n\t]+", "", str(c)) for c in df.columns]

        # 兼容英文列名或别称 -> 中文模板列名
        rename_map = {
            'q_type': '题型',
            '题目类型': '题型',
            '类型': '题型',
            'content': '题干',
            '题目内容': '题干',
            '题干内容': '题干',
            '题目': '题干',
            'option_a': 'A',
            '选项A': 'A',
            'option_b': 'B',
            '选项B': 'B',
            'option_c': 'C',
            '选项C': 'C',
            'option_d': 'D',
            '选项D': 'D',
            'answer': '答案',
            '正确答案': '答案',
            'explain': '解析',
            '解析说明': '解析',
        }
        df = df.rename(columns=rename_map)

        # 调试用，报错时看终端真实列名
        print("Excel列名:", [repr(c) for c in df.columns])

        required = ['题型', '题干', '答案']
        missing = [c for c in required if c not in df.columns]
        if missing:
            flash('导入失败：Excel列名不正确或缺少必要列：' + ', '.join(missing)
                  + '。当前列名：' + ', '.join(list(df.columns)))
            return render_template('import.html')

        # 去掉完全空行
        df = df.dropna(how='all')

        for _, row in df.iterrows():
            q = Question(
                q_type=clean_value(row['题型']).strip(),
                content=clean_value(row['题干']).strip(),
                option_a=clean_value(row.get('A', '') or '').strip(),
                option_b=clean_value(row.get('B', '') or '').strip(),
                option_c=clean_value(row.get('C', '') or '').strip(),
                option_d=clean_value(row.get('D', '') or '').strip(),
                answer=clean_value(row['答案']).strip(),
                explain=clean_value(row.get('解析', '') or '').strip()
            )
            db.session.add(q)

        try:
            db.session.commit()
            flash(f'{file.filename}题库导入成功')
        except Exception as e:
            db.session.rollback()
            flash('导入失败：' + str(e))

    return render_template('import.html')

def clean_value(v):
    if v is None:
        return ''
    if isinstance(v, float) and v != v:  # NaN判断
        return ''
    s = str(v).strip()
    if s.lower() == 'nan':
        return ''
    return s

# 管理员：用户管理（列表/添加/删除）
@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if current_user.role != 'admin':
        return '无权限', 403

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            role = request.form.get('role', 'student')

            if not username or not password:
                flash('用户名和密码不能为空')
            elif User.query.filter_by(username=username).first():
                flash('用户名已存在')
            else:
                user = User(
                    username=username,
                    password=generate_password_hash(password),
                    role=role
                )
                db.session.add(user)
                db.session.commit()
                flash('用户添加成功')

        elif action == 'delete':
            user_id = request.form.get('user_id')
            try:
                user_id = int(user_id)
            except:
                flash('无效的用户ID')
                return redirect(url_for('admin_users'))
            user = User.query.get(int(user_id))
            if user and user.id != current_user.id:
                db.session.delete(user)
                db.session.commit()
                flash('用户已删除')
            elif user and user.id == current_user.id:
                flash('不能删除自己')
            else:
                flash('用户不存在')

        return redirect(url_for('admin_users'))

    users = User.query.all()
    return render_template('admin_users.html', users=users)


# 我的错题
@app.route('/my_wrong')
@login_required
def my_wrong():
    wrongs = WrongQuestion.query.filter_by(user_id=current_user.id).order_by(WrongQuestion.last_wrong_time.desc()).all()
    questions = []
    for w in wrongs:
        q = Question.query.get(w.question_id)
        if q:
            questions.append(q)
    return render_template('my_wrong.html', questions=questions, wrongs=wrongs)


# 我的收藏
@app.route('/my_favorites')
@login_required
def my_favorites():
    favorites = FavoriteQuestion.query.filter_by(user_id=current_user.id).all()
    questions = []
    fav_ids = set()
    for f in favorites:
        q = Question.query.get(f.question_id)
        if q:
            questions.append(q)
            fav_ids.add(q.id)
    return render_template('my_favorites.html', questions=questions, fav_ids=fav_ids)


# 收藏/取消收藏
@app.route('/toggle_favorite/<int:question_id>', methods=['GET', 'POST'])
@login_required
def toggle_favorite(question_id):
    fav = FavoriteQuestion.query.filter_by(
        user_id=current_user.id,
        question_id=question_id
    ).first()

    if fav:
        db.session.delete(fav)
        flash('已取消收藏')
        favorited = False
    else:
        db.session.add(FavoriteQuestion(
            user_id=current_user.id,
            question_id=question_id
        ))
        flash('收藏成功')
        favorited = True

    db.session.commit()

    # 如果是 JS/fetch POST，返回 json
    if request.method == 'POST':
        return {'favorited': favorited}

    # 普通页面点击/收藏页点击，跳回去
    return redirect(request.referrer or url_for('my_favorites'))

#简单管理列表页面/删除入口
@app.route('/admin/question-list')
@login_required
def admin_question_list():
    if current_user.role != 'admin':
        return '无权限'
    questions = Question.query.all()
    return render_template('admin_questions.html', questions=questions)

#删除路由
@app.route('/admin/question/delete/<int:qid>', methods=['POST'])
@login_required
def delete_question(qid):
    if current_user.role != 'admin':
        return '无权限'
    q = Question.query.get_or_404(qid)
    db.session.delete(q)
    db.session.commit()
    flash('题目已删除')
    return redirect(url_for('admin_question_list'))

@app.route('/admin/question/clear', methods=['POST'])
@login_required
def clear_questions():
    if current_user.role != 'admin':
        flash('无权限')
        return redirect(url_for('admin_question_list'))

    try:
        Question.query.delete()
        db.session.commit()
        flash('题库已清空（全部题目已删除）')
    except Exception as e:
        db.session.rollback()
        flash('清空失败：' + str(e))

    return redirect(url_for('admin_question_list'))

# 初始化数据库，首次启动自动创建表+内置管理员账号
with app.app_context():
    db.create_all()
    # 自动创建默认管理员：账号admin 密码123456
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
        # 内置3道演示电工真题
        demo_q1 = Question(q_type='判断', content='电流的方向规定为正电荷移动的方向', answer='A', option_a='正确',
                           option_b='错误')
        demo_q2 = Question(q_type='单选', content='低压电工证复审年限是多少年？', answer='B', option_a='1年',
                           option_b='3年', option_c='5年', option_d='6年')
        demo_q3 = Question(q_type='单选', content='我国标准规定工频安全电压有效值的限值是多少？', answer='A',
                           option_a='50V', option_b='36V', option_c='24V', option_d='12V')
        db.session.add_all([demo_q1, demo_q2, demo_q3])
        db.session.commit()


if __name__ == '__main__':
    #app.run(debug=True, host='0.0.0.0', port=5002)
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)