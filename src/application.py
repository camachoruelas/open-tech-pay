from flask import render_template, jsonify, request, url_for
from flask_migrate import Migrate
from src import app, db
from src.models import *
from src.model_schemas import *
from src.request_schemas import *
import high_level_methods as hlm
import json

migrate = Migrate(app, db)


@app.route('/')
def index():
    return render_template('app.html', is_debug=app.config['DEBUG'])


@app.route('/fetch_fields')
def fetch_fields():
    perks = Perk.query.filter(Perk.listed).all()
    employment_types = EmploymentType.query.all()
    roles = Role.query.filter(Role.listed).all()
    educations = Education.query.all()
    techs = Tech.query.filter(Tech.listed).all()

    return jsonify({
        'perks': [PerkSchema().dump(model).data for model in perks],
        'employment_types': [EmploymentTypeSchema().dump(model).data for model in employment_types],
        'roles': [RoleSchema().dump(model).data for model in roles],
        'educations': [EducationSchema().dump(model).data for model in educations],
        'techs': [TechSchema().dump(model).data for model in techs],
    })


@app.route('/fetch_submissions')
def fetch_submissions():
    submissions = Submission.query.filter(Submission.confirmed).all()
    schema = SubmissionSchema(only={
        'salary',
        'employment_type',
        'perks',
        'roles',
        'education',
        'techs',
        'years_experience',
        'years_with_current_employer',
        'number_of_employers',
        'verified'
    })
    result = [schema.dump(submission).data for submission in submissions]
    return jsonify(result)


@app.route('/check_email')
def check_email():
    request_schema = CheckEmailRequestSchema().load(request.args)
    if len(request_schema.errors) > 0:
        return jsonify({
            'status': 'error'
        })

    result = hlm.check_email(request_schema.data['email'])
    result.pop('in_use', None) # Otherwise, it would be very easy to check if an employee/coworker has submitted.
    result['status'] = 'ok'
    return jsonify(result)


@app.route('/submit', methods=['POST'])
def submit():
    payload = json.loads(request.form['payload'])

    """ Perform basic validation on the request params """
    request_schema = SubmissionRequestSchema().load(payload)
    if len(request_schema.errors) > 0:
        return jsonify({
            'status': 'error',
            'errors': request_schema.errors.items()
        })

    """ Overwriting existing unconfirmed submission, otherwise create a new one """
    submission = Submission.query.filter(
        Submission.email == payload['email']
    ).first()

    if submission:
        # This is quite hacky. Notice the "instance" key in the passed param.
        data = request_schema.data
        data['instance'] = submission
        submission = SubmissionSchema(only=[
            'instance',
            'salary',
            'email',
            'years_experience',
            'years_with_current_employer',
            'number_of_employers'
        ]).load(data).data
    else:
        submission = SubmissionSchema(only=[
            'salary',
            'email',
            'years_experience',
            'years_with_current_employer',
            'number_of_employers'
        ]).load(request_schema.data).data

    """ Load PayRange, Eduction, EmploymentType """
    employment_type = EmploymentType.query.filter(EmploymentType.id == payload['employment_type']).first()
    education = Education.query.filter(Education.id == payload['education']).first()

    submission.perks = []
    submission.roles = []
    submission.techs = []

    """ Get Perk models """
    for perk_dict in payload['perks']:
        if 'id' in perk_dict:
            perk = Perk.query.filter(Perk.id == perk_dict['id']).first()

        elif 'name' in perk_dict:
            perk = Perk.query.filter(Perk.name == perk_dict['name']).first()
            if not perk:
                perk = Perk(name=perk_dict['name'], listed=False)

        if perk:
            if 'value' in perk_dict:
                # Add perk with value
                submission.submission_to_perks.append(SubmissionToPerk(perk, value=perk_dict['value']))

            else:
                # Add perk without value
                submission.perks.append(perk)

    """ Get Role models """
    for role_dict in payload['roles']:
        if 'id' in role_dict:
            role = Role.query.filter(Role.id == role_dict['id']).first()

        elif 'name' in role_dict:
            role = Role.query.filter(Role.name == role_dict['name']).first()
            if not role:
                role = Role(name=role_dict['name'], listed=False)

        if role:
            submission.roles.append(role)

    """ Get Tech models """
    for tech_dict in payload['techs']:
        if 'id' in tech_dict:
            tech = Tech.query.filter(Tech.id == tech_dict['id']).first()

        elif 'name' in tech_dict:
            tech = Tech.query.filter(Tech.name == tech_dict['name']).first()
            if not tech:
                tech = Tech(name=tech_dict['name'], listed=False)

        if tech:
            submission.techs.append(tech)

    if len(submission.roles) == 0:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'errors': ['No roles selected']
        })

    submission.employment_type = employment_type
    submission.education = education
    submission.confirmed = False
    submission.confirmation_code = hlm.get_confirmation_code()

    db.session.add(submission)
    db.session.commit()

    """ Send confirmation email """
    # https://pythonhosted.org/flask-mail/
    from flask_mail import Mail, Message
    mail = Mail(app)
    msg = Message("OpenPay London Submission Confirmation",
                  sender="noreply@londontechpay.ca",
                  recipients=[submission.email])
    msg.body = url_for('confirm', _external=True, confirmation_code=submission.confirmation_code)
    mail.send(msg)

    return jsonify({
        'status': 'ok'
    })


@app.route('/confirm')
def confirm():
    request_schema = ConfirmRequestSchema().load(request.args)
    succeeded = False
    if not request_schema.errors:
        succeeded = hlm.confirm_submission(request.args['confirmation_code']) is not None

    return render_template('confirm.html', succeeded=succeeded)
