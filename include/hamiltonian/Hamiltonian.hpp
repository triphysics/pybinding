#pragma once
#include "support/dense.hpp"
#include "support/sparse.hpp"
#include "support/traits.hpp"
#include "support/uref.hpp"

namespace tbm {

class HamiltonianVisitor;
class System;
class HamiltonianModifiers;

/**
 Builds and stores a tight-binding Hamiltonian. Abstract base.
 */
class Hamiltonian {
public:
    virtual ~Hamiltonian() = default;

    virtual SparseURef matrix_union() const = 0;
    virtual int non_zeros() const = 0;

    std::string report;
};


/// Concrete hamiltonian with a specific scalar type.
template<typename scalar_t>
class HamiltonianT : public Hamiltonian {
    using real_t = num::get_real_t<scalar_t>;
    using complex_t = num::get_complex_t<scalar_t>;
    using SparseMatrix = SparseMatrixX<scalar_t>;

public:
    HamiltonianT(const System& s, const HamiltonianModifiers& m, const Cartesian& k_vector);
    virtual ~HamiltonianT() override;

    /// Get a const reference to the matrix.
    const SparseMatrix& get_matrix() const { return matrix; }

    virtual SparseURef matrix_union() const override { return matrix; }
    virtual int non_zeros() const override { return matrix.nonZeros(); }

private: // build the Hamiltonian
    void build_main(const System& s, const HamiltonianModifiers& m);
    void build_periodic(const System& s, const HamiltonianModifiers& m);
    void set(const Cartesian& k_vector);

private:
    SparseMatrix matrix; ///< the sparse matrix that holds the data
    std::vector<SparseMatrix> boundary_matrices;
    std::vector<Cartesian> boundary_lengths;
};

extern template class HamiltonianT<float>;
extern template class HamiltonianT<std::complex<float>>;
//extern template class HamiltonianT<double>;
//extern template class HamiltonianT<std::complex<double>>;

} // namespace tbm
