import oncotext.utils.date as date
import re
import pdb
import copy
import uuid

def remove_bad_chars(text):
    text = re.sub(r"_x000D_", " ", text)
    text = re.sub(r"_x0009_", " ", text)
    text = re.sub(r"_x000d_", " ", text)
    return text

def preprocess_text(text):
    text = str(text)
    text = re.sub(r"[^\w\.\+=]", " ", text)
    text = ' '.join(text.split('\n'))
    text = re.sub(r"(----)+", " ", text)
    text = re.sub(r"(====)+", " ", text)
    text = text.lower()
    text = re.sub(r"_x000d_", " ", text)
    text = re.sub(r"_x009d_", " ", text)
    return text

def segment_left_right(txt):
    leftTxt = ""
    rightTxt = ""

    leftIndx = txt.lower().index("left") if "left" in txt.lower() else len(txt)
    rightIndx = txt.lower().index("right") if "right" in txt.lower() else len(txt)

    leadTxtIndx = min(rightIndx, leftIndx)
    leftTxt += txt[:leadTxtIndx]
    rightTxt += txt[:leadTxtIndx]
    mode = "left" if leftIndx < rightIndx else "right"
    txt = txt[leadTxtIndx:]
    while "left" in txt.lower() or "right" in txt.lower():
        leftIndx = txt.lower().index("left") if "left" in txt.lower() else len(txt)
        rightIndx = txt.lower().index("right") if "right" in txt.lower() else len(txt)

        leadTxtIndx = rightIndx if mode == "left" else leftIndx

        if mode == "left":
            leftTxt += txt[:leadTxtIndx]
        else:
            rightTxt += txt[:leadTxtIndx]

        txt = txt[leadTxtIndx:]

        mode = "right" if mode == "left" else "left"

    return {"l": leftTxt, "r": rightTxt}

def is_bilateral(text):
    '''
        params: text- lowercase text
        returns: True if report is believed to be bilateral

    '''
    bilat = "breast" in text and "right" in text and "left" in text
    return bilat

def segment_breast(report, raw_text_key, preprocessed_text_key, side_key, logger):
    '''
        If report is bilateral, split into two reports. else return single
        report.

        params:
        - report: full text repot
        - raw_text_key: key for full text
        - preprocessed_text_key: key for full text
        - side_key: where to store side information
        - logger

        returns:
        -segmented_reports: list of reports
    '''
    segmented_reports = []

    full_text = preprocess_text(report[raw_text_key])

    contains_side_annotation = side_key in report

    if is_bilateral(full_text):
        segmented_text = segment_left_right(full_text)
        if contains_side_annotation:
            segmented_r = copy.deepcopy(report)
            segmented_r[preprocessed_text_key] = segmented_text[report[side_key]]
            segmented_reports = [segmented_r]
        else:
            for side, s_text in segmented_text.items():
                segmented_r = copy.deepcopy(report)
                segmented_r[side_key] = side
                segmented_r[preprocessed_text_key] = s_text
                segmented_reports.append(segmented_r)
    else:
        report[preprocessed_text_key] = full_text
        segmented_reports = [report]

    return segmented_reports


def segment_prostate(report, raw_text_key, preprocessed_text_key, segment_id_key, segment_type_key, logger):

    full_text = report[raw_text_key]
    header = copy.deepcopy(report)
    diags = copy.deepcopy(report)
    footer = copy.deepcopy(report)

    hindx = full_text.lower().find("diagnosis")
    hindx = full_text.rfind("\n", 0, hindx)
    header[preprocessed_text_key] = preprocess_text(full_text[ :hindx])
    header[segment_type_key] = "Header"
    header[segment_id_key] = "Header"

    m = re.search("md|m\.d|clinical history|clinical data|specimens submitted|tissue submitted|gross desciption|slide\-block description", full_text.lower()[hindx: ])
    if m:
        dindx = m.start() + hindx
    else:
        dindx = hindx
    dindx = full_text.rfind("\n", hindx, dindx)
    diags[preprocessed_text_key] = full_text[hindx:dindx]
    
    footer[preprocessed_text_key] = preprocess_text(full_text[dindx: ])
    footer[segment_type_key] = "Description"
    footer[segment_id_key] = "Description"

    segmented_dict = {header[segment_id_key]: header,
                      footer[segment_id_key]: footer} 
    
    segments = [["", ""]]
    for line in diags[preprocessed_text_key].split("\n"):
        m = re.search('^[A-Z]\. ', line)
        if m:
            if segments[0][1] == "":
                segments[0][0] += line[3: ]+"\n"
                segments[0][1] = m.group(0)[ :-1]
            else:
                segments.append([line[3: ]+"\n", m.group(0)[ :-1]])
        else:
            segments[-1][0] += line+"\n"

    if len(segments) == 1:
        segments = [["", ""]]
        alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for line in diags[preprocessed_text_key].split("\n"):
            m = re.search('^((\s)+)?PROSTATE ', line)
            if m:
                if segments[0][1] == "":
                    segments[0][0] += line+"\n"
                    segments[0][1] = alpha[0]+"."
                else:
                    segment_name = alpha[len(segments)%len(alpha)]
                    segments.append([line+"\n", segment_name + "."])
            else:
                segments[-1][0] += line+"\n"
        
            
    for tup in segments:
        r = copy.deepcopy(report)
        r[preprocessed_text_key] = preprocess_text(tup[0])
        r[segment_type_key] = "Diagnosis"
        r[segment_id_key] = tup[1]
        segmented_dict[r[segment_id_key]] = r
        
    if segment_id_key in report:
        segmented_reports = [segmented_dict[report[segment_id_key]]]
    else:
        segmented_reports = [segmented_dict[k] for k in segmented_dict]
        
    return segmented_reports

def segment_reports(r, organ, raw_text_key, preprocessed_text_key, side_key, segment_id_key, segment_type_key, logger):
    if organ == "OrganBreast":
        segmented_reports = segment_breast(r, raw_text_key, preprocessed_text_key, side_key, logger)
    elif organ == "OrganProstateCore":
        segmented_reports = segment_prostate(r, raw_text_key, preprocessed_text_key, segment_id_key, segment_type_key, logger)
    else:
        r[preprocessed_text_key] = preprocess_text(r[raw_text_key])
        segmented_reports = [r]

    return segmented_reports

            
def set_uuid(report):
    if not 'ID' in report:
        report['ID'] = str(uuid.uuid4())
    if 'MRN_Type' in report:
        report['Institution'] = report['MRN_Type']
    elif not 'Institution' in report:
        report['Institution'] = 'Unknown'

    if 'MRNPlusX' in report and not 'MRN' in report:
        report['MRN'] = report['MRNPlusX']
    if not 'MRN' in report:
        report['MRN'] = 'Unknown'

    if 'EMPI' not in report:
        report['EMPI'] = '999999999'

    return report

def remove_none_vals(report):
    keys = list(report.keys())
    for key in keys:
        if report[key] is None:
            del report[key]
    return report

def apply_rules(reports, organ, raw_text_key, preprocessed_text_key, time_key, side_key, segment_id_key, segment_type_key, logger):
    '''
        Go through list of reports and do the following:
        - Segement into left/right
        - lower case and throw away non alpha neumeric characters
        - throw away reports with no text
        - add uuid

        params:
        - reports: list of dicts (each dict is a report) to operate over
        - raw_text_key: key for raw report text
        - preprocessed_text_key: key to store preprocess_text report text
        - logger: pylogger object

        returns:
        preprocessed_reports: a preprocess reports list
    '''
    preprocessed_reports = []
    for r in reports:
        # Skip reports with no text in it
        if raw_text_key not in r and preprocessed_text_key not in r:
            logger.warn("preprocess - report has no {} field.".format(raw_text_key))
            continue
        r[raw_text_key] = r[raw_text_key] if raw_text_key in r else r[preprocessed_text_key]
        r[raw_text_key] = remove_bad_chars(r[raw_text_key])

        if organ == 'Meta':
            r[preprocessed_text_key] = r[raw_text_key]

        if preprocessed_text_key in r:
            r[preprocessed_text_key] = preprocess_text(r[preprocessed_text_key])
            preprocessed_reports.append(r)
        else:
            segmented_reports = segment_reports(r, organ, raw_text_key, preprocessed_text_key, side_key, segment_id_key, segment_type_key, logger)
            preprocessed_reports.extend(segmented_reports)
                
    preprocessed_reports = [date.set_timestamp(report, time_key, logger) for report in preprocessed_reports]

    preprocessed_reports = [remove_none_vals(report) for report in preprocessed_reports ]

    preprocessed_reports = [set_uuid(report) for report in preprocessed_reports ]

    return preprocessed_reports

def remove_duplicates(reports, raw_text_key, preprocessed_text_key, logger):
    '''
        Go through list of reports and remove all duplicates.
        Remove elements of preprocessed text_key

        unique_reports: a reports list with no duplicate report[raw_text_key]
    '''

    unique_report_dict = {}

    for r in reports:
        if preprocessed_text_key in r:
            del r[preprocessed_text_key]
        unique_report_dict[ r[raw_text_key] ] = r

    unique_reports = [ v for k,v in unique_report_dict.items() ]
    return unique_reports
