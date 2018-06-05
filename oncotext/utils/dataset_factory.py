import random
import oncotext.datasets.pathology_classification_dataset
import oncotext.datasets.pathology_tagging_dataset
import pickle
import numpy as np

def get_oncotext_dataset_train(all_reports, label_maps, args, text_key):
    reports = [r for r in all_reports if args.aspect in r ]
    random.shuffle(reports)
    if len(reports) == 0:
        raise Exception("No data found for {}".format(args.aspect))
    split_indx = int(len(reports)* args.train_split)
    train_reports = reports[: split_indx]
    dev_reports = reports[split_indx:]

    if label_maps[args.aspect][0] == "NUM":
        dataset_obj = oncotext.datasets.pathology_tagging_dataset.PathologyTaggingDataset
    else:
        dataset_obj = oncotext.datasets.pathology_classification_dataset.PathologyClassificationDataset
        
    train_data = dataset_obj(args, train_reports, label_maps, text_key, 'train')
    dev_data = dataset_obj(args, dev_reports, label_maps, text_key, 'dev')
    
    return train_data, dev_data


def get_oncotext_dataset_test(reports, label_maps, args, text_key):
    if label_maps[args.aspect][0] == "NUM":
        dataset_obj = oncotext.datasets.pathology_tagging_dataset.PathologyTaggingDataset
    else:
        dataset_obj = oncotext.datasets.pathology_classification_dataset.PathologyClassificationDataset
        
    test_data = dataset_obj(args, reports, label_maps, text_key, 'test')        
    return test_data


def get_embedding_tensor(config, args):
    embeddings =  pickle.load(open(config['EMBEDDING_PATH'],'rb'))
    args.embedding_dim = embeddings.shape[1]
    return embeddings


def predsToLabels(preds, test_data, label_maps, diagnosis, args, text_key, logger):
    if label_maps[diagnosis][0] == "NUM":
        try:
            preds = np.reshape(preds, (len(test_data), args.max_length))
        except Exception as e:
            logger.warn("RN Wrapper. {} model returned incorrectly sized labels {}! Following Exception({}). Populating all reports with 0 label".format(diagnosis, (len(preds), len(test_data)), e))
            preds = np.zeros((len(test_data), args.max_length), dtype=int)

        for i in range(len(test_data)):
            if 1 in preds[i]:
                text = test_data.dataset[i][text_key].split()
                inds = np.where(preds[i]== 1)[0]
                if len(inds) > 0:
                    prediction = ""
                    for ind in inds:
                        if ind < len(text):
                            prediction += text[ind]
                else:
                    prediction = "0"
                test_data.dataset[i][diagnosis] = prediction
            else:
                test_data.dataset[i][diagnosis] = "0"
    else:
        for i in range(len(test_data)):
            prediction = label_maps[diagnosis][preds[i]]
            test_data.dataset[i][diagnosis] = prediction

    return test_data.dataset
