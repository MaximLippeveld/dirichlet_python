from __future__ import division

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.preprocessing import label_binarize
from sklearn.metrics import log_loss

from scipy.optimize import minimize


class MultinomialRegression(BaseEstimator, RegressorMixin):
    def __init__(self, weights_0=None, bounds=None):
        self.coef_ = None
        self.intercept_ = None
        self.weights_0_ = weights_0
        self.bounds_ = None

    def fit(self, X, y, *args, **kwargs):

        X_ = np.hstack((X, np.ones((len(X), 1))))

        classes = np.unique(y)
        k = len(classes)
        target = label_binarize(y, classes)
        if k == 2:
            target = np.hstack([target, 1-target])

        if self.weights_0_ is None:
            weights_0 = np.random.randn(k + 1, k - 1)
            weights_0[np.diag_indices(k - 1)] = np.abs(weights_0[np.diag_indices(k - 1)])
            weights_0[k - 1] = np.abs(weights_0[k - 1]) * -1
        else:
            weights_0 = self.weights_0_

        weights_0 = weights_0.transpose().ravel()

        # if self.bounds_ is None:
        #    dims = (k+1, k-1)
        #    diag_ravel_ind = np.ravel_multi_index(np.diag_indices(k-1), dims)

        #    k_ind = [np.ones(k-1, dtype=int)*(k-1), np.arange(k-1)]
        #    k_ravel_ind = np.ravel_multi_index(k_ind, dims)

        #    bounds = []
        #    for ind, _ in enumerate(weights_0):
        #        if ind in diag_ravel_ind:
        #            bounds.append((0, np.inf))
        #        elif ind in k_ravel_ind:
        #            bounds.append((-np.inf, 0))
        #        else:
        #            bounds.append((-np.inf, np.inf))
        # else:
        #    bounds = self.bounds_

        res = minimize(
            method='trust-exact',
            fun=_objective,
            jac=_gradient,
            hess=_hessian,
            x0=weights_0,
            args=(X_, target, k),
            bounds=None,
            #tol=1e-16,
            options={'disp': False,
                     'initial_trust_radius': 1.0,
                     'max_trust_radius': 1e32,
                     'change_ratio': 1 - 1e-3,
                     'eta': 0.0,
                     'maxiter': 1e4,
                     'gtol': 1e-8}
        )

        weights = res.x

        print('===================================================================')
        if res.success:
            print('optimisation converged!')
        else:
            print('optimisation not converged!')

        np.set_printoptions(precision=3)
        print('gradient is:')
        print(_gradient(weights, X_, target, k).reshape(-1, k+1).transpose())
        print('mean target is:')
        print(np.mean(target, axis=0))
        print('mean output is:')
        print(np.mean(_calculate_outputs(_get_weights(weights, k), X_), axis=0))
        print('reason for termination:')
        print(res.message)
        print('===================================================================')

        self.weights_ = _get_weights(weights, k)
        self.coef_ = self.weights_.transpose()[:, :-1]
        self.intercept_ = self.weights_.transpose()[:, -1]
        return self

    def predict_proba(self, S):
        S_ = np.hstack((S, np.ones((len(S), 1))))
        return _calculate_outputs(self.weights_, S_)

    def predict(self, S):
        return self.predict_proba(S)


def _get_weights(params, k):
    n_params = len(params)
    if n_params == k ** 2 - 1:
        return params.reshape(-1, k + 1).transpose()
    else:
        value = params[-1]
        intercepts = params[:-1]
        weights = np.zeros((k + 1, k - 1))
        weights[np.diag_indices(k - 1)] = value
        weights[k - 1] = value * -1
        weights[k] = intercepts
        return weights


def _objective(params, *args):
    (X, y, k) = args
    weights = _get_weights(params, k)
    outputs = _calculate_outputs(weights, X)
    loss = log_loss(y, outputs)
    #print('Loss is:')
    #print(loss)
    #print('Parameter is:')
    #print(weights)
    return loss


def _gradient(params, *args):
    (X, y, k) = args
    weights = _get_weights(params, k)
    outputs = _calculate_outputs(weights, X)
    graident = np.zeros((k + 1, k - 1))
    for i in range(0, k - 1):
        graident[:, i] = np.sum((outputs[:, i] - y[:, i]).reshape(-1, 1).repeat(k+1, axis=1) * X, axis=0)
    #print(graident)
    return graident.transpose().ravel()


def _hessian(params, *args):
    (X, y, k) = args
    weights = _get_weights(params, k)
    outputs = _calculate_outputs(weights, X)
    hessian = np.zeros((k**2 - 1, k**2 - 1))
    n = np.shape(X)[0]
    XXT = np.zeros((n, k+1, k+1))
    for i in range(0, n):
        XXT[i, :, :] = np.matmul(X[i, :].reshape(-1, 1), X[i, :].reshape(-1, 1).transpose())
    for i in range(0, k-1):
        for j in range(0, k-1):
            if i <= j:
                tmp_diff = outputs[:, i] * (int(i == j) - outputs[:, j])
                tmp_diff = tmp_diff.ravel().repeat((k+1)**2).reshape(n, k+1, k+1)
                hessian[i*(k+1):(i+1)*(k+1), j*(k+1):(j+1)*(k+1)] = np.sum(tmp_diff * XXT, axis=0)
            else:
                hessian[i*(k+1):(i+1)*(k+1), j*(k+1):(j+1)*(k+1)] = hessian[j*(k+1):(j+1)*(k+1), i*(k+1):(i+1)*(k+1)]

    #np.set_printoptions(precision=1)
    #print('hessian is:')
    #if not (np.all(np.linalg.eigvals(hessian) > 0)):
    #    print('non-positive-definite Hessian is detected!')
    #print(hessian)
    return hessian


def _calculate_outputs(weights, X):
    k = len(weights) - 1
    mul = np.zeros((len(X), k))
    mul[:, :k - 1] = np.dot(X, weights)
    return _softmax(mul)


def _softmax(X):
    """Compute the softmax of matrix X in a numerically stable way."""
    shiftx = X - np.max(X, axis=1).reshape(-1, 1)
    exps = np.exp(shiftx)
    return exps / np.sum(exps, axis=1).reshape(-1, 1)
