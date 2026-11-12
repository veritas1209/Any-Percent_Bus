"""Optional compiled sparse Dijkstra; the Python and Dart routing rules stay identical."""
try:
    import numpy as np
    from scipy import __version__ as SCIPY_VERSION
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
except ImportError:
    np=None
    SCIPY_VERSION=None


class NativeGraph:
    def __init__(self,offsets,neighbors,weights):
        self.offsets=np.asarray(offsets,dtype=np.int32)
        self.neighbors=np.asarray(neighbors,dtype=np.int32)
        self.weights=np.asarray(weights,dtype=np.float64)
        self.nodes=len(offsets)-1

    def distances(self,seeds,limit):
        if not seeds:return np.full(self.nodes,np.inf)
        nodes=sorted(seeds)
        offsets=np.append(self.offsets,np.int32(len(self.neighbors)+len(nodes)))
        neighbors=np.concatenate((self.neighbors,np.asarray(nodes,dtype=np.int32)))
        weights=np.concatenate((self.weights,np.asarray([seeds[n] for n in nodes],dtype=np.float64)))
        graph=csr_matrix((weights,neighbors,offsets),shape=(self.nodes+1,self.nodes+1))
        return dijkstra(graph,directed=True,indices=self.nodes,limit=max(0,limit))[:self.nodes]


def make_native_graph(offsets,neighbors,weights):
    return None if np is None else NativeGraph(offsets,neighbors,weights)
