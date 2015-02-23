#pragma once
#include "result/Result.hpp"
#include "support/dense.hpp"
#include "support/physics.hpp"
#include <vector>

namespace tbm {

class LDOSpoint : public Result {
public:
    LDOSpoint(ArrayXd energy, float broadening, Cartesian position,
              short sublattice = -1, std::vector<Cartesian> k_path = {});

    virtual void visit(const Solver* solver) override;
    virtual void visit(Greens* greens) override;

public:
    const ArrayX<float>& get_ldos() const { return ldos; }
    const ArrayX<float>& get_energy() const { return energy; }

protected:
    ArrayX<float> calc_ldos(const Solver* solver);
    ArrayX<float> calc_ldos(Greens* greens);
    
protected:
    ArrayX<float> energy;
    ArrayX<float> ldos;
    
    const float broadening;
    const Cartesian target_position;
    const short target_sublattice;
    const std::vector<Cartesian> k_path;
};

} // namespace tbm
