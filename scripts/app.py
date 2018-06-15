import os, shutil
from os.path import dirname, realpath
import sys
sys.path.append(dirname(dirname(realpath(__file__))))
sys.path.append(os.path.join(dirname(dirname(realpath(__file__))),
                             'text_nn'))
import oncotext.logger as logger
from flask import Flask
from flask import request, json, jsonify
import oncotext.rationale_net_wrapper as rationale_net_wrapper
import oncotext.utils.postprocess as postprocess
import oncotext.utils.preprocess as preprocess
import oncotext.utils.generic as generic
import oncotext.utils.json as json_utils
import oncotext.evaluation as evaluation
import pickle
import pdb

app = Flask(__name__)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
LOGPATH = os.environ['LOGFILE']
LOGNAME = 'oncotext'
CONFIG_NAME = 'config.Config'
app.config.from_object(CONFIG_NAME)
# create logger
config = app.config

app = Flask(__name__)
app.config.from_object(__name__)
logger = logger.get_logger(LOGNAME, LOGPATH)

DB_TRAIN_PATH = config['DB_TRAIN_PATH'].split(".")[0]
DB_UNLABLED_PATH = config['DB_UNLABLED_PATH'].split(".")[0]
DEFAULT_USER = config['DEFAULT_USERNAME']
DEFAULT_ORGAN = config['DEFAULT_ORGAN']

SUCCESS_MSG = "Request Success"
TRAIN_SUCCESS_MSG = "Request Success. Dev results returned"
NOP_MSG = "Request No Op. Invalid arg"
NO_SUCH_USR_MSG = "Error! User {} doesn't have a {} db initialized!"



@app.route("/addTrain", methods=['POST'])
def addTrainData():
    '''
        Add a list of reports to training items for a given system user.
        params:
        - data: list of reports with values for at least one current diagnosis
        - name: ID of user, used to identify which data to use.
        returns:
            message, status code
    '''
    data = json.loads(request.data) or []
    name = request.args.get("name") or DEFAULT_USER
    organ = request.args.get("organ") or DEFAULT_ORGAN

    data = preprocess.apply_rules(data,
                                  organ,
                                  config['RAW_REPORT_TEXT_KEY'],
                                  config['PREPROCESSED_REPORT_TEXT_KEY'],
                                  config['REPORT_TIME_KEY'],
                                  config['SIDE_KEY'],
                                  config['SEGMENT_ID_KEY'],
                                  config['SEGMENT_TYPE_KEY'],
                                  logger)

    if len(data) == 0 or not generic.contains_annotations(data, config):
        logger.warn("addTrain[ - did not include any reports with labels. No op.")
        return NOP_MSG

    logger.info( "addTrain - data has keys {}".format( data[0].keys()))
    logger.info("addTrain - [{}] len data {}".format(name, len(data)))

    filename = DB_TRAIN_PATH+"_"+organ+".p"
    if os.path.isfile(filename):
        db_train = pickle.load(open(filename, 'rb'), encoding='bytes')
    else:
        db_train = {}
        
    if name not in db_train:
        logger.info("Adding {} to db_train_{}".format(name, organ))
        default_train = pickle.load(open(config['DB_BASE_PATH'],'rb'), encoding='bytes')
        db_train[name] = default_train[organ] if organ in default_train else []        

    db_train[name].extend(data)

    logger.info("addTrain - Len train[{}] {}".format(name, len(db_train[name])))
    pickle.dump(db_train, open(filename, 'wb'))

    return SUCCESS_MSG, 200


@app.route("/addUnlabeled", methods=['POST'])
def addUnlabeledData():
    '''
        Add reports to label for the given system user.
        params:
        - data: list of reports with Report_Text, and Report_Date_Time
        - name: ID of user, used to identify which data to use.
        returns:
            message, status code
    '''
    data = json.loads(request.data) or []

    if len(data) == 0:
        logger.warn("addUnlabeled - did not include any reports. No op.")
        return NOP_MSG

    name = request.args.get("name") or DEFAULT_USER
    organ = request.args.get("organ") or DEFAULT_ORGAN

    filename = DB_UNLABLED_PATH+"_"+organ+".p"
    if os.path.isfile(filename):
        db_unlabeled = pickle.load(open(filename, 'rb'), encoding='bytes')
    else:
        db_unlabeled = {}
        
    if name not in db_unlabeled:
        logger.info( "addUnlabeled - Adding {} to db_unlabeled_{}".format(name, organ))
        db_unlabeled[name] = []

    data = preprocess.apply_rules(data,
                                  organ,
                                  config['RAW_REPORT_TEXT_KEY'],
                                  config['PREPROCESSED_REPORT_TEXT_KEY'],
                                  config['REPORT_TIME_KEY'],
                                  config['SIDE_KEY'],
                                  config['SEGMENT_ID_KEY'],
                                  config['SEGMENT_TYPE_KEY'],
                                  logger)

    if organ == config['META_KEY']:
        logger.info( "addUnlabeled - Adding {} reports to db_unlabeled".format(len(data)))
        db_unlabeled[name].extend(data)
    else:
        logger.info( "addUnlabeled - Re-writing {} reports to db_unlabeled".format(len(data)))
        db_unlabeled[name] = data

    pickle.dump(db_unlabeled, open(filename, 'wb'))
    logger.info("addUnlabeled - db redumped to path {}".format(filename))
    
    return SUCCESS_MSG, 200


@app.route("/train", methods=['GET'])
def train():
    '''
        Launches ML model to retrain on current data on db_train[model]
        for all diagnoses.
        params: - name: ID of user, used to identify which data to use.
        returns:- dev_results, msg, status code
    '''
    name = request.args.get("name") or DEFAULT_USER
    organ = request.args.get("organ") or DEFAULT_ORGAN

    filename = DB_TRAIN_PATH+"_"+organ+".p"
    db_train = pickle.load(open(filename, 'rb'))
    
    if name not in db_train:
        return NO_SUCH_USR_MSG.format(name, 'train'), 500
    
    result_dict = rationale_net_wrapper.train(name, organ, db_train[name], config, logger)

    return json.dumps({'results': result_dict,
            'msg':TRAIN_SUCCESS_MSG}), 200


# Kicks off job to run model on the corresping data
# Will return all unlabeled data
@app.route("/predict", methods=['GET'])
def predict():
    '''
        Launches ML model to label on current data on db_predict[model]
        for all diagnoses.
        params: - name: ID of user, used to identify which data to use.
                - eval_sets: list of lists of reports to evaluate predictions
                    on
                - debug: Set to "True" to skip running nn code
        returns:- labeled_db, results, msg, status code
    '''
    name = request.args.get("name") or DEFAULT_USER
    organ = request.args.get("organ") or DEFAULT_ORGAN
    try:
        eval_sets = json.loads(request.data.decode())
    except Exception as e:
        eval_sets = {}
        logger.warn("No eval sets provided for prediction!")
        
    filename = DB_UNLABLED_PATH+"_"+organ+".p"
    db_unlabeled = pickle.load(open(filename, 'rb'))

    if name not in db_unlabeled:
        return NO_SUCH_USR_MSG.format(name, 'unlabeled'), 500

    reportDB = rationale_net_wrapper.label_reports(name,
                                                   organ,
                                                   db_unlabeled[name],
                                                   config,
                                                   logger)

    pickle.dump(reportDB, open(os.path.join(config['PICKLE_DIR'], 'reportDBAPI_labeled_intermediate_'+organ+'.p'), 'wb'))
    # reportDB = pickle.load(open(os.path.join(config['PICKLE_DIR'], 'reportDBAPI_labeled_intermediate_'+organ+'.p'), 'rb'))

    train_filename = DB_TRAIN_PATH+"_"+organ+".p"
    train_db = pickle.load(open(train_filename, 'rb'))
    if name in train_db:
        user_train_db = train_db[name]
    else:
        user_train_db = []

    reportDB = postprocess.apply_rules(reportDB,
                                       user_train_db,
                                       organ,
                                       config,
                                       logger)
    
    results = evaluation.evaluate(reportDB, eval_sets, config, logger)
    
    return json.dumps({'reportDB': json_utils.make_json_compliant(reportDB),
                       'results': results,
                       'msg': SUCCESS_MSG})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config['PORT'])

