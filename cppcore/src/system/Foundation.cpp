#include "system/Foundation.hpp"
#include "system/Shape.hpp"

#include <Eigen/Dense>  // for `colPivHouseholderQr()`

namespace tbm {

Foundation::Foundation(Lattice const& lattice, Primitive const& primitive)
    : lattice(lattice)
{
    size = primitive.size;
    size_n = static_cast<int>(lattice.sublattices.size());

    auto const origin = [&]{
        Cartesian width = Cartesian::Zero();
        for (auto i = 0u; i < lattice.vectors.size(); ++i) {
            width += static_cast<float>(size[i] - 1) * lattice.vectors[i];
        }
        return static_cast<Cartesian>( - width / 2);
    }();

    num_sites = size.prod() * size_n;
    init_positions(origin);
    is_valid.setConstant(num_sites, true);
    init_neighbor_count();
}

Foundation::Foundation(Lattice const& lattice, Shape const& shape)
    : lattice(lattice)
{
    auto const bounds = find_bounds(lattice, shape);
    size = (bounds.second - bounds.first) + Index3D::Ones();
    size_n = static_cast<int>(lattice.sublattices.size());

    Cartesian origin = shape.offset;
    for (auto i = 0u; i < lattice.vectors.size(); ++i) {
        origin += static_cast<float>(bounds.first[i]) * lattice.vectors[i];
    }

    num_sites = size.prod() * size_n;
    init_positions(origin);
    is_valid = shape.contains(positions);
    init_neighbor_count();

    trim_edges();
}

FoundationIterator Foundation::begin() {
    return {this, 0};
}

FoundationIterator Foundation::end() {
    return {this, num_sites};
}

SliceIterator Foundation::Slice::begin() {
    return {foundation, index};
}

SliceIterator Foundation::Slice::end() {
    return {foundation};
}

std::pair<Index3D, Index3D> Foundation::find_bounds(Lattice const& lattice,
                                                    Shape const& shape) {
    auto const ndim = lattice.vectors.size();
    auto const lattice_matrix = [&]{
        Eigen::MatrixXf m(ndim, ndim);
        for (auto i = 0u; i < ndim; ++i) {
            m.col(i) = lattice.vectors[i].head(ndim);
        }
        return m;
    }();

    Array3i lower_bound = Array3i::Constant(std::numeric_limits<int>::max());
    Array3i upper_bound = Array3i::Constant(std::numeric_limits<int>::min());
    for (auto const& point : shape.vertices) {
        // Translate Cartesian coordinates `p` into lattice vector coordinates `v`
        // -> solve `A*v = p`, where A is `lattice_matrix`
        auto const& p = point.head(ndim);
        Array3i v = Array3i::Zero();
        v.head(ndim) = lattice_matrix.colPivHouseholderQr().solve(p).cast<int>();

        lower_bound = (v < lower_bound).select(v, lower_bound);
        upper_bound = (v > upper_bound).select(v, upper_bound);
    }

    // Add +/- 1 padding to compensate for `cast<int>()` truncation
    lower_bound.head(ndim) -= 1;
    upper_bound.head(ndim) += 1;

    return {lower_bound, upper_bound};
}

void Foundation::init_positions(Cartesian origin) {
    positions.resize(num_sites);
    for (auto& site : *this) {
        positions[site.idx] = calculate_position(site, origin);
    }
}

void Foundation::init_neighbor_count() {
    neighbour_count.resize(num_sites);

    for (auto& site : *this) {
        auto const& sublattice = lattice[site.sublattice];
        auto num_neighbors = static_cast<int16_t>(sublattice.hoppings.size());

        // Reduce the neighbor count for sites on the edges
        for (auto const& hopping : sublattice.hoppings) {
            auto const index = (site.index + hopping.relative_index).array();
            if (any_of(index < 0) || any_of(index >= size.array()))
                num_neighbors -= 1;
        }

        neighbour_count[site.idx] = num_neighbors;
    }
}

void Foundation::trim_edges() {
    for (auto& site : *this) {
        if (!site.is_valid())
            clear_neighbors(site);
    }
}

Cartesian Foundation::calculate_position(Site const& site, Cartesian origin) const {
    Cartesian position = origin;
    // + unit cell position (Bravais lattice)
    for (std::size_t i = 0; i < lattice.vectors.size(); ++i) {
        position += static_cast<float>(site.index[i]) * lattice.vectors[i];
    }
    // + sublattice offset
    position += lattice[site.sublattice].offset;
    return position;
}

void Foundation::clear_neighbors(Site& site) {
    if (site.get_neighbor_count() == 0)
        return;

    site.for_each_neighbour([&](Site neighbor, Hopping) {
        if (!neighbor.is_valid())
            return;

        neighbor.set_neighbor_count(neighbor.get_neighbor_count() - 1);
        if (neighbor.get_neighbor_count() < lattice.min_neighbours) {
            neighbor.set_valid(false);
            clear_neighbors(neighbor); // recursive call... but it will not be very deep
        }
    });

    site.set_neighbor_count(0);
}

int Foundation::finalize()
{
    neighbour_count.resize(0); // not needed any more

    // Count the number of valid sites and assign a Hamiltonian index to them
    hamiltonian_indices = ArrayX<int32_t>::Constant(num_sites, -1);
    auto num_valid_sites = 0;
    for (int i = 0; i < num_sites; ++i) {
        if (is_valid[i])
            hamiltonian_indices[i] = num_valid_sites++;
    }

    return num_valid_sites;
}

ArrayX<sub_id> Foundation::make_sublattice_ids() const {
    ArrayX<sub_id> sublattice_ids(num_sites);

    auto const max_id = static_cast<sub_id>(lattice.sublattices.size());
    for (auto i = 0; i < num_sites;) {
        for (auto id = sub_id{0}; id < max_id; ++id, ++i) {
            sublattice_ids[i] = id;
        }
    }

    return sublattice_ids;
}

} // namespace tbm
