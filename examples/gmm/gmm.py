import matplotlib
matplotlib.use('Agg')
from matplotlib import mlab
import matplotlib.pyplot as plt
import six

import numpy as np

import cupy


def estimate_gaussian_parameters(X, xp, resp):
    nk = xp.sum(resp, axis=0)
    means = xp.dot(resp.T, X) / nk[:, None]
    avg_X2 = xp.dot(resp.T, X * X) / nk[:, None]
    avg_X_means = means * xp.dot(resp.T, X) / nk[:, None]
    covariances = avg_X2 - 2 * avg_X_means + means ** 2
    return nk / len(X), means, covariances


def estimate_log_prob(X, xp, inv_cov, means):
    n_features = X.shape[1]
    log_det = xp.sum(xp.log(inv_cov), axis=1)
    precisions = inv_cov ** 2
    log_prob = xp.sum((means ** 2 * precisions), 1) - \
        2 * xp.dot(X, (means * precisions).T) + xp.dot(X ** 2, precisions.T)
    return -0.5 * (n_features * xp.log(2 * np.pi) + log_prob) + log_det


def e_step(X, xp, inv_cov, means, weights):
    weighted_log_prob = estimate_log_prob(X, xp, inv_cov, means) + \
        xp.log(weights)
    log_prob_norm = xp.log(xp.sum(xp.exp(weighted_log_prob), axis=1))
    log_resp = weighted_log_prob - log_prob_norm[:, None]
    return xp.mean(log_prob_norm), log_resp


def m_step(X, xp, log_resp):
    weights, means, covariances = \
        estimate_gaussian_parameters(X, xp, xp.exp(log_resp))
    inv_cov = 1 / xp.sqrt(covariances)
    return weights, means, covariances, inv_cov


def train_gmm(X, max_iter, tol):
    xp = cupy.get_array_module(X)
    lower_bound = -np.infty
    converged = False
    weights = xp.array([0.5, 0.5], dtype=np.float32)
    mean1 = xp.random.normal(3, xp.array([1, 2]), size=2)
    mean2 = xp.random.normal(-3, xp.array([2, 1]), size=2)
    means = xp.stack((mean1, mean2))
    covariances = xp.random.rand(2, 2)
    inv_cov = 1 / xp.sqrt(covariances)

    for n_iter in six.moves.range(max_iter):
        prev_lower_bound = lower_bound
        log_prob_norm, log_resp = e_step(X, xp, inv_cov, means, weights)
        weights, means, covariances, inv_cov = m_step(X, xp, log_resp)
        lower_bound = log_prob_norm
        change = lower_bound - prev_lower_bound
        if abs(change) < tol:
            converged = True
            break

    if not converged:
        msg = 'Failed to converge. Try different init parameters' \
              'or increase max_iter, tol or check for degenerate data.'
        print(msg)

    return inv_cov, means, weights, covariances


def predict(X, inv_cov, means, weights):
    xp = cupy.get_array_module(X)
    log_prob = estimate_log_prob(X, xp, inv_cov, means)
    return (log_prob + xp.log(weights)).argmax(axis=1)


def draw(X, pred, means, covariances, output):
    xp = cupy.get_array_module(X)
    for i in six.moves.range(2):
        labels = X[pred == i]
        if xp == cupy:
            labels = labels.get()
        plt.scatter(labels[:, 0], labels[:, 1], color=np.random.rand(3, 1))
    if xp == cupy:
        means = means.get()
        covariances = covariances.get()
    plt.scatter(means[:, 0], means[:, 1], s=120, marker='s', facecolors='y',
                edgecolors='k')
    x = np.linspace(-10, 10, 1000)
    y = np.linspace(-10, 10, 1000)
    X, Y = np.meshgrid(x, y)
    for i in six.moves.range(2):
        Z = mlab.bivariate_normal(X, Y, np.sqrt(covariances[i][0]),
                                  np.sqrt(covariances[i][1]),
                                  means[i][0], means[i][1])
        plt.contour(X, Y, Z)
    plt.savefig(output + '.png')
