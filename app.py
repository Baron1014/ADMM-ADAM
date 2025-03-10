from scipy.io import loadmat, savemat
#from scipy.linalg import block_diag
from scipy.sparse import csc_matrix, block_diag
import numpy as np
from numpy import linalg as LA
#from PIL import Image
import datetime
from tqdm import tqdm

def main():
    # load dataset
    x3dl = loadmat('dataset/X3DL.mat')
    mask = loadmat('dataset/mask.mat')
    ottawa = loadmat('dataset/Ottawa.mat')
    X3D_corrupted = ottawa['X3D_ref'] * mask['mask_3D']
    print(X3D_corrupted.shape)
    X3d_rec = ADMM_ADAM(X3D_corrupted, mask['mask_3D'], x3dl['X3D_DL'])

    print(x3dl.keys())
    print(mask.keys())
    print(ottawa.keys())
    print("X3D_DL: ", x3dl['X3D_DL'].shape)
    print("mask_3D: ", mask['mask_3D'].shape)
    print("X3D_ref: ", ottawa['X3D_ref'].shape)

    # save mat
    savemat('dataset/X3D_rec.mat', {'X3D_rec':X3d_rec})


def ADMM_ADAM(X3D_corrupted, mask, x3dl):
    now = datetime.datetime.now()
    # para
    N=10 # dimension of the hyperspectral subspace
    lam=0.01 # regularization parameter
    mu=1e-3 # ADMM penalty parameter 

    # compute S_DL 
    row, col , all_bands = X3D_corrupted.shape
    spatial_len=row*col
    X2D_DL = x3dl.reshape((-1,all_bands), order='F').T
    # Compute E
    E = compute_basis(x3dl, N)
    S_DL = np.dot(E.T, X2D_DL)

    ## ADMM
    mask_2D = mask.reshape((spatial_len,all_bands), order='F').T
    nz_idx = np.zeros((173,1))
    nz_idx[0] = 1
    print("start kron...")
    M_idx = np.kron(mask_2D, nz_idx)
    print('end kron...')
    M = M_idx[:172**2, :]
    PtransP = M.reshape((172, 172, -1), order='F')# omega
    RP_tensor = np.einsum('kij, lk -> lij', PtransP, E.T) # (172,172,65536) (10, 172)
    RRtrps_tensor = np.einsum('ikj, lk -> ilj', RP_tensor, E.T) # (10,172,65536) (10, 172)
    savemat('dataset/tensor.mat', {"RP_tensor":RP_tensor, 'RRtrps_tensor':RRtrps_tensor})

    X2D_corrupted = X3D_corrupted.reshape((-1, all_bands), order='F').T
    # When updating S, bring the latter term into R to simplify the result
    RPY = np.zeros((10, 1, 65536))
    for i in range(spatial_len):
        RPY[:,:,i] = np.dot(RP_tensor[:, :, i], X2D_corrupted[:,i].reshape((-1,1), order='F'))
    RPy = RPY.reshape((-1,1), order='F')
    # RR'
    RRtrps_per = np.transpose(RRtrps_tensor, (2,0,1))
    # Compute I
    I = mu/2 * np.eye(N)
    block = np.zeros(RRtrps_per.shape)
    # When updating S, the calculation process of the preceding item
    for i in range(RRtrps_per.shape[0]):
        block[i,:,:] = LA.inv(RRtrps_per[i,:,:].reshape((10, -1), order='F') + I)
    block_3D = np.transpose(block, (1,2,0))
    b = [csc_matrix(block_3D[:, :, n]) for n in range(block_3D.shape[2])]
    S_left = block_diag((b))

    for i in tqdm(range(50), desc="update s"):
        if i ==0:
            # init S2D and D
            S2D = np.zeros((N,spatial_len))
            D=np.zeros((N,spatial_len))
        # update Z
        Z = (1/(mu+lam))*(lam*S_DL+mu*(S2D-D))
        # delta calculations
        DELTA = (Z+D)
        delta = DELTA.reshape((-1,1), order='F')
        # right term calculations
        s_right = RPy + (mu/2)*delta
        # update S
        s = S_left@s_right
        S2D = s.reshape((N,65536), order='F')   
        # update D
        D = D - S2D + Z 
    # restore image ＝ E * S2D 
    X2D_rec=np.dot(E, S2D)
    X3D_rec = X2D_rec.T.reshape((256,256,172), order='F')

    print(f"cost time: {datetime.datetime.now()-now}")

    return X3D_rec

def compute_basis(x3dl, N):
    X = x3dl.reshape((-1, x3dl.shape[2]), order='F')
    M = X.shape[1]
    _, eV = LA.eigh(np.dot(X.T, X))
    E = eV[:,M-N:]

    return E


if __name__=="__main__":
    main()
