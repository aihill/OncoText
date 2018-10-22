from datetime import datetime as date
import sys, os
import numpy as np
from csv import DictWriter
import pdb
import smtplib
import string
import sklearn
import oncotext.utils.preprocess as preprocess
import oncotext.utils.generic as generic
import sklearn.metrics

def score_on_test_set(reports, test_set, organ, config, logger):
    gold_reports = preprocess.apply_rules(
        test_set,
        organ,
        config['RAW_REPORT_TEXT_KEY'],
        config['PREPROCESSED_REPORT_TEXT_KEY'],
        config['REPORT_TIME_KEY'],
        config['SIDE_KEY'],
        config['SEGMENT_ID_KEY'],
        config['SEGMENT_TYPE_KEY'],
        logger)
    
    raw_text_key = config["RAW_REPORT_TEXT_KEY"]
    preprocessed_text_key = config['PREPROCESSED_REPORT_TEXT_KEY']
    side_key = config["SIDE_KEY"] if organ == "OrganBreast" else config["SEGMENT_ID_KEY"]
    diagnoses = config['POST_DIAGNOSES'][organ]

    text_to_gold = {}
    for r in gold_reports:
        side = r[side_key] if side_key in r else ""
        text = r[raw_text_key] + side
        text_to_gold[ text ] = r

    logger.info("evaluation - test set has {} unique preprocessed texts".format(len(text_to_gold)))

    text_to_pred = {}
    for r in reports:
        side = r[side_key] if side_key in r else ""
        text = r[raw_text_key] + side
        text_to_pred[text] = r
    logger.info("evaluation - filename filtered report set has {} unique preprocessed texts".format(len(text_to_pred)))

    texts = [t for t in text_to_pred if t in text_to_gold]
    results = []
    keys = ['NAME', 'ACCURACY', 'PRECISION', 'RECALL', 'F1']
    for d in diagnoses:
        res = {'NAME':d}

        preds = [text_to_pred[t][d] for t in texts if d in text_to_pred[t] and d in text_to_gold[t]]
        golds =  [text_to_gold[t][d] for t in texts if d in text_to_pred[t] and d in text_to_gold[t]]
                
        if len(preds) == 0 or len(golds) == 0:
            logger.warn("evaluation [{}] - skipping because num preds {}, num golds {}".format(d, len(preds), len(golds)))
            continue

        res['ACCURACY'] = sklearn.metrics.accuracy_score(preds, golds)
        try:
            preds = [int(val) for val in preds]
            golds = [int(val) for val in golds]
            
            res['PRECISION'] = sklearn.metrics.precision_score(preds, golds, average="weighted")
            res['RECALL'] = sklearn.metrics.recall_score(preds, golds, average="weighted")
            res['F1'] = sklearn.metrics.f1_score(preds, golds, average="weighted")
        except Exception as e:
            logger.warn("Cant commpute Precis, Recall, F1 for {}, because of: {}".format(d, e))
            res['PRECISION'] = 'NA'
            res['RECALL'] = 'NA'
            res['F1'] = 'NA'

        results.append(res)

    overallRes = {'NAME':'AVERAGE'}
    overallRes['ACCURACY'] = np.mean([r['ACCURACY'] for r in results])
    overallRes['PRECISION'] = 'NA'
    overallRes['RECALL'] = 'NA'
    overallRes['F1'] = 'NA'

    results.append(overallRes)

    return results, keys


def evaluate(reportDB, eval_sets, organ, config, logger):
    all_results = {}

    for file_name in eval_sets:
        test_set = eval_sets[file_name]
        relevant_reports = [r for r in reportDB if r['filename'] == file_name]
        logger.info("Scoring reportDB against test_set {}".format(file_name))
        logger.info("Scoring reportDB has {} records matching  test_set {} records".format(len(relevant_reports), len(test_set)))
        results, result_keys = score_on_test_set(relevant_reports, test_set, organ, config, logger)
        all_results[file_name]= results

    return all_results
