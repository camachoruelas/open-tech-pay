from flask import render_template, jsonify, request, url_for
from flask_migrate import Migrate
from src import app, db
from src.models import *
from src.model_mappings import *
from src.request_schemas import *
import high_level_methods as hlm
import json

migrate = Migrate(app, db)

@app.route('/')
def index():
    return render_template('app.html')

@app.route('/fetch_fields')
def fetch_fields():
    perks = Perk.query.filter(Perk.listed).all()
    pay_ranges = PayRange.query.all()
    employment_types = EmploymentType.query.all()
    roles = Role.query.filter(Role.listed).all()
    educations = Education.query.all()
    techs = Tech.query.filter(Tech.listed).all()

    return jsonify({
        'pay_ranges': [PayRangeSchema().dump(model).data for model in pay_ranges],
        'perks': [PerkSchema().dump(model).data for model in perks],
        'employment_types': [EmploymentTypeSchema().dump(model).data for model in employment_types],
        'roles': [RoleSchema().dump(model).data for model in roles],
        'educations': [EducationSchema().dump(model).data for model in educations],
        'techs': [TechSchema().dump(model).data for model in techs],
    })


@app.route('/fetch_submissions')
def fetch_submissions():
    submissions = Submission.query.filter(Submission.confirmed).all()
    schema = SubmissionSchema()
    result = [schema.dump(submission).data for submission in submissions]
    return jsonify(result)


@app.route('/check_email')
def check_email():
    request_schema = CheckEmailSchema().load(request.args)
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
    malformed_request_error = jsonify({
        'status': 'error',
        'errors': ['Malformed request']
    })

    payload = json.loads(request.form['payload'])

    """ Check if the request contains all expected relationship fields """
    expected_relationship_fields = [
        'perks', 'roles', 'techs',
        'pay_range', 'education', 'employment_type'
    ]
    for field in expected_relationship_fields:
        if not field in payload:
            return malformed_request_error

    """ Try creating the submission """
    """ First, try validating"""
    submission_schema = SubmissionSchema(only=[
        'email',
        'years_experience',
        'years_with_current_employer',
        'number_of_employers'
    ])
    errors = submission_schema.validate(payload)
    if len(errors) > 0:
        return jsonify({
            'status': 'error',
            'errors': [value for key, value in errors.items()]
        })
    """ Overwriting existing unconfirmed submission, otherwise create a new one """
    submission = Submission.query.filter(
        Submission.email == payload['email']
    ).first()
    if submission and submission.confirmed:
        return jsonify({
            'status': 'error',
            'errors': ['Submission for this email already exists']
        })
    elif submission:
        # This is quite hacky. Notice the "instance" key in the passed param.
        submission_schema = SubmissionSchema(only=[
            'instance',
            'email',
            'years_experience',
            'years_with_current_employer',
            'number_of_employers'
        ])
        payload['instance'] = submission
        submission = submission_schema.load(payload).data
    else:
        submission = submission_schema.load(payload).data

    """ Load PayRange, Eduction, EmploymentType """
    pay_range = PayRange.query.filter(PayRange.id == payload['pay_range']).first()
    employment_type = EmploymentType.query.filter(EmploymentType.id == payload['employment_type']).first()
    education = Education.query.filter(Education.id == payload['education']).first()
    if not pay_range or not employment_type or not education:
        return malformed_request_error

    """ Get Perk models """
    perks = []
    for perk_dict in payload['perks']:
        if 'id' in perk_dict:
            perk = Perk.query.filter(Perk.id == perk_dict['id']).first()

        elif 'name' in perk_dict:
            perk = Perk.query.filter(Perk.name == perk_dict['name']).first()
            if not perk:
                perk = Perk(name=perk_dict['name'], listed=False)

        if perk:
            db.session.add(perk)
            perks.append(perk)

    """ Get Role models """
    roles = []
    for role_dict in payload['roles']:
        if 'id' in role_dict:
            role = Role.query.filter(Role.id == role_dict['id']).first()

        elif 'name' in role_dict:
            role = Role.query.filter(Role.name == role_dict['name']).first()
            if not role:
                role = Role(name=role_dict['name'], listed=False)

        if role:
            db.session.add(role)
            roles.append(role)

    """ Get Tech models """
    techs = []
    for tech_dict in payload['techs']:
        if 'id' in tech_dict:
            tech = Tech.query.filter(Tech.id == tech_dict['id']).first()

        elif 'name' in tech_dict:
            tech = Tech.query.filter(Tech.name == tech_dict['name']).first()
            if not tech:
                tech = Tech(name=tech_dict['name'], listed=False)

        if tech:
            db.session.add(tech)
            techs.append(tech)

    if len(perks) == 0 or len(roles) == 0 or len(techs) == 0:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'errors': ['No roles, perks, or technologies selected']
        })

    submission.pay_range = pay_range
    submission.employment_type = employment_type
    submission.education = education
    submission.perks = perks
    submission.roles = roles
    submission.tech = techs
    submission.confirmed = False
    submission.confirmation_code = hlm.get_confirmation_code()

    db.session.add(submission)
    db.session.commit()

    print 'Created submission {} with confirmation code {}'.format(submission.id, submission.confirmation_code)
    print url_for('confirm', _external=True, confirmation_code=submission.confirmation_code)

    """ Send confirmation email """
    # https://pythonhosted.org/flask-mail/
    # from flask_mail import Mail, Message
    # mail = Mail(app)
    # msg = Message("OpenPay London Submission Confirmation",
    #               sender="noreply@openpay-placeholder.com",
    #               recipients=[submission.email])
    # mail.send(msg)

    return jsonify({
        'status': 'ok'
    })


@app.route('/confirm')
def confirm():
    request_schema = ConfirmSchema().load(request.args)
    succeeded = False
    if not request_schema.errors:
        succeeded = hlm.confirm_submission(request.args['confirmation_code']) is not None

    return render_template('confirm.html', succeeded=succeeded)
