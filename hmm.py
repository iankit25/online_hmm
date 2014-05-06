import copy
import distributions
import em
import kmeans
import numpy as np
import matplotlib.pyplot as plt
import sys
from numpy import newaxis as nax
from numpy.linalg import det, inv

def logsumexp(a, axis=None):
    a_max = np.max(a, axis=axis)
    try:
        return a_max + np.log(np.sum(np.exp(a - a_max), axis=axis))
    except:
        return a_max + np.log(np.sum(np.exp(a - a_max[:,nax]), axis=axis))

def alpha_beta(X, pi, A, obs_distr):
    '''A[i,j] = p(z_{t+1} = j | z_t = i)'''
    T = X.shape[0]
    K = pi.shape[0]
    lalpha = np.zeros((T, K))
    lbeta = np.zeros((T, K))
    lA = np.log(A)
    lemissions = np.zeros((T,K))
    for k in range(K):
        lemissions[:,k] = obs_distr[k].log_pdf(X)

    lalpha[0,:] = np.log(pi) + lemissions[0,:]
    for t in range(1,T):
        a = lalpha[t-1:t,:].T + lA + lemissions[t,:]
        lalpha[t,:] = logsumexp(a, axis=0)

    lbeta[T-1,:] = np.zeros(K)
    for t in reversed(range(T-1)):
        b = lbeta[t+1,:] + lA + lemissions[t+1,:]
        lbeta[t,:] = logsumexp(b, axis=1)

    return lalpha, lbeta

def viterbi(X, pi, A, obs_distr):
    T = X.shape[0]
    K = pi.shape[0]
    lgamma = np.zeros((T,K))
    back = np.zeros((T,K))  # back-pointers
    lA = np.log(A)
    lemissions = np.zeros((T,K))
    for k in range(K):
        lemissions[:,k] = obs_distr[k].log_pdf(X)

    lgamma[0,:] = np.log(pi) + lemissions[0,:]
    for t in range(1,T):
        a = lgamma[t-1:t,:].T + lA + lemissions[t,:]
        lgamma[t,:] = np.max(a, axis=0)
        ss = np.sum(lgamma[t,:] == a, axis=0)
        if np.max(ss) > 1:
            print ss, t
        back[t,:] = np.argmax(a, axis=0)

    # recover MAP from back-pointers
    seq = [int(np.argmax(lgamma[T-1,:]))]
    for t in reversed(range(1, T)):
        seq.append(back[t,seq[-1]])

    return list(reversed(seq))

def smoothing(lalpha, lbeta):
    '''Computes all the p(q_t | u_1, ..., u_T)'''
    log_p = lalpha + lbeta
    return log_p - logsumexp(log_p, axis=1)[:,nax]

def pairwise_smoothing(X, lalpha, lbeta, A, obs_distr):
    '''returns log_p[t,i,j] = log p(q_t = i, q_{t+1} = j|u)'''
    T, K = lalpha.shape
    lA = np.log(A)
    lemissions = np.zeros((T,K))
    for k in range(K):
        lemissions[:,k] = obs_distr[k].log_pdf(X)

    log_p = np.zeros((T,K,K))
    for t in range(T-1):
        log_p[t,:,:] = lalpha[t:t+1,:].T + lA + lemissions[t+1,:] + lbeta[t+1,:]

    log_p2 = log_p.reshape(T, K*K)
    log_p = np.reshape(log_p2 - logsumexp(log_p2, axis=1)[:,nax],
                       (T,K,K))

    return log_p

def log_likelihood(lalpha, lbeta):
    '''p(u_1, ..., u_T) = \sum_i alpha_T(i) beta_T(i)'''
    T = lalpha.shape[0]
    return logsumexp(lalpha[T-1,:] + lbeta[T-1,:])

def em_hmm(X, pi, init_obs_distr, n_iter=10, Xtest=None):
    pi = pi.copy()
    obs_distr = copy.deepcopy(init_obs_distr)
    T = X.shape[0]
    K = len(obs_distr)

    A = 1. / K * np.ones((K,K))

    ll_train = []
    ll_test = []

    lalpha, lbeta = alpha_beta(X, pi, A, obs_distr)
    ll_train.append(log_likelihood(lalpha, lbeta))
    if Xtest is not None:
        lalpha_test, lbeta_test = alpha_beta(Xtest, pi, A, obs_distr)
        ll_test.append(log_likelihood(lalpha_test, lbeta_test))

    for it in range(n_iter):
        # E-step
        tau = np.exp(smoothing(lalpha, lbeta))
        tau_pairs = np.exp(pairwise_smoothing(X, lalpha, lbeta, A, obs_distr))

        # M-step
        pi = tau[0,:] / np.sum(tau[0,:])

        A = np.sum(tau_pairs, axis=0)
        A = A / np.sum(A, axis=1)

        for j in range(K):
            obs_distr[j].max_likelihood(X, tau[:,j])

        lalpha, lbeta = alpha_beta(X, pi, A, obs_distr)
        ll_train.append(log_likelihood(lalpha, lbeta))
        if Xtest is not None:
            lalpha_test, lbeta_test = alpha_beta(Xtest, pi, A, obs_distr)
            ll_test.append(log_likelihood(lalpha_test, lbeta_test))

    return tau, A, obs_distr, pi, ll_train, ll_test

if __name__ == '__main__':
    X = np.loadtxt('EMGaussian.data')
    Xtest = np.loadtxt('EMGaussian.test')
    K = 4

    # Run simple EM (no HMM)
    iterations = 40
    assignments, centers, _ = kmeans.kmeans_best_of_n(X, K, n_trials=5)
    new_centers = [distributions.Gaussian(c.mean, np.eye(2)) \
                for c in centers]
    tau, obs_distr, pi, gmm_ll_train, gmm_ll_test = \
            em.em(X, new_centers, assignments, n_iter=iterations, Xtest=Xtest)

    # example with fixed parameters
    A = 1. / 6 * np.ones((K,K))
    A[np.diag(np.ones(K)) == 1] = 0.5

    lalpha, lbeta = alpha_beta(Xtest, pi, A, obs_distr)
    log_p = smoothing(lalpha, lbeta)
    p = np.exp(log_p)

    def plot_traj(p):
        plt.figure()
        ind = np.arange(100)
        for k in range(K):
            plt.subplot(K,1,k+1)
            plt.bar(ind, p[:100,k])

    plot_traj(p)

    # EM for the HMM
    tau, A, obs_distr, pi, ll_train, ll_test = \
            em_hmm(X, pi, obs_distr, Xtest=Xtest)

    plt.figure()
    plt.plot(ll_train, label='training')
    plt.plot(ll_test, label='test')
    plt.xlabel('iterations')
    plt.ylabel('log-likelihood')
    plt.legend()

    # print all log-likelihoods
    print '{:<14} {:>14} {:>14}'.format('', 'train', 'test')
    print '{:<14} {:>14.3f} {:>14.3f}'.format('General GMM', gmm_ll_train[-1], gmm_ll_test[-1])
    print '{:<14} {:>14.3f} {:>14.3f}'.format('HMM', ll_train[-1], ll_test[-1])

    # Viterbi
    seq = viterbi(X, pi, A, obs_distr)
    plt.figure()
    plt.scatter(X[:,0], X[:,1], c=seq)
    plt.title('most likely sequence, training')
    seq_test = viterbi(Xtest, pi, A, obs_distr)
    plt.figure()
    plt.scatter(Xtest[:,0], Xtest[:,1], c=seq_test)
    plt.title('most likely sequence, test')

    # marginals in each state
    lalpha, lbeta = alpha_beta(Xtest, pi, A, obs_distr)
    log_p = smoothing(lalpha, lbeta)
    plot_traj(np.exp(log_p))

    def plot_traj(p):
        plt.figure()
        ind = np.arange(100)
        for k in range(K):
            plt.subplot(K,1,k+1)
            plt.bar(ind, p[:100,k])

    # most likely state according to marginals vs viterbi
    plt.figure()
    ind = np.arange(100)
    c = ['b', 'g', 'r', 'y']
    plt.subplot(211)
    for k in range(K):
        plt.bar(ind, k == np.argmax(log_p[:100], axis=1), color=c[k])
    plt.title('marginals')

    plt.subplot(212)
    for k in range(K):
        plt.bar(ind, k == np.array(seq_test[:100]), color=c[k])
    plt.title('marginals')
