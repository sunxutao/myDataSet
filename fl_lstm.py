import numpy as np
import logging
from utils import create_model, AvgrageMeter, lstm_train, lstm_evaluation, lstm_localization
import time
import torch.optim as optim
import copy

def aggregation(data_train, data_test, args, clientIDs, model, optimizer):
    mean_train_acc, mean_train_loss = AvgrageMeter(), AvgrageMeter()
    mean_test_acc, mean_test_loss = AvgrageMeter(), AvgrageMeter()

    initial_weights = copy.deepcopy(model.state_dict())

    num_examples = []
    weight_dict_list = []

    for clientID in clientIDs:
        model.load_state_dict(initial_weights)
        model, train_acc, train_loss, test_acc_list, test_loss_list=lstm_train(data_train[clientID],
                                    data_test[clientID], args, model, optimizer, args.lstm_epochs)
        num_examples.append(len(data_train[clientID]))
        # load state_dict for each client
        weight_dict_list.append(copy.deepcopy(model.state_dict()))
        mean_train_acc.update(train_acc, 1)
        mean_train_loss.update(train_loss, 1)
        mean_test_acc.update(test_acc_list[-1], 1)
        mean_test_loss.update(test_loss_list[-1], 1)

    # fedAveraging
    for key in weight_dict_list[0].keys():
        weight_dict_list[0][key] *= num_examples[0]
        for model_id in range(1, len(weight_dict_list)):
            weight_dict_list[0][key].add_(weight_dict_list[model_id][key] * num_examples[model_id])
        weight_dict_list[0][key].div_(np.sum(num_examples))

    return weight_dict_list[0], mean_train_acc.avg, mean_train_loss.avg, mean_test_acc.avg, mean_test_loss.avg


def FL_LSTM(dsupport_train, dsupport_test, dtest_train, dtest_test, args):
    # filter unqualified client sets
    # print('Before filter:')
    # print('number_support_client: {}' .format(len(dsupport_train)))
    # print('number_test_client: {}'.format(len(dtest_train)))
    support_train = [dsupport_train[i] for i in range(len(dsupport_train))
                     if (len(dsupport_train[i]) > 1 and len(dsupport_test[i]) > 1)]
    support_test = [dsupport_test[i] for i in range(len(dsupport_train))
                    if (len(dsupport_train[i]) > 1 and len(dsupport_test[i]) > 1)]
    test_train = [dtest_train[i] for i in range(len(dtest_train))
                  if len(dtest_train[i]) > 1 and len(dtest_test[i]) > 1]
    test_test = [dtest_test[i] for i in range(len(dtest_train))
                 if len(dtest_train[i]) > 1 and len(dtest_test[i]) > 1]
    # print('After filter:')
    logging.info('number_support_client: {}'.format(len(support_train)))
    logging.info('number_test_client: {}'.format(len(test_train)))

    # number of selected clients per round
    num_clients = int(args.lstm_fraction * len(support_train))
    logging.info('number_selected_clients_per_round: {}'.format(num_clients))

    print('FL:\n')

    # initial model
    model = create_model(args)
    optimizer = optim.SGD(model.parameters(), lr=args.lstm_lr)

    # FL iterations
    for round_num in range(1, args.num_rounds + 1):
        # Train on support client sets
        clientIDs = np.random.choice(range(len(support_train)), num_clients, replace=False)
        weights, train_acc, train_loss, acc1, loss1 = aggregation(support_train, support_test, args, clientIDs, model, optimizer)
        model.load_state_dict(weights)

        # log info
        logging.info('round {:2d}: support_train_acc {:.6f}, support_train_loss {:.6f}, support_test_acc {:.6f}, '
                     'support_test_loss {:.6f}'.format(round_num, train_acc, train_loss, acc1, loss1))

        if round_num % args.local_interval == 0:
            # Eval on test client sets with current weights
            acc2, loss2 = lstm_evaluation(test_test, args, model)
            # log info
            logging.info('initial_acc {:.6f}, initial_loss {:.6f}'.format(acc2, loss2))

            # Eval on test client sets with localization
            acc3, loss3, test_acc, test_loss = lstm_localization(test_train, test_test, args, model, optimizer)
            # log info
            logging.info('localization_acc {:.6f}, localization_loss {:.6f}'.format(acc3, loss3))
            for i in range(len(test_acc)):
                logging.info(
                    'epoch: {:2d}: test acc: {:.6f}, test loss: {:.6f}'.format(i + 1, test_acc[i], test_loss[i]))

    return