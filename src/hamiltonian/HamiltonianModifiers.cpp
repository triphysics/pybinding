#include "hamiltonian/HamiltonianModifiers.hpp"
using namespace tbm;

bool HamiltonianModifiers::add_unique(const std::shared_ptr<const OnsiteModifier>& m) {
    if (std::find(onsite.begin(), onsite.end(), m) == onsite.end()) {
        onsite.push_back(m);
        return true;
    }
    return false;
}

bool HamiltonianModifiers::add_unique(const std::shared_ptr<const HoppingModifier>& m) {
    if (std::find(hopping.begin(), hopping.end(), m) == hopping.end()) {
        hopping.push_back(m);
        return true;
    }
    return false;
}

bool HamiltonianModifiers::any_complex() const {
    const auto complex_potential = std::any_of(
        onsite.begin(), onsite.end(),
        [](const std::shared_ptr<const OnsiteModifier>& o) { return o->is_complex(); }
    );

    auto const complex_hoppings = std::any_of(
        hopping.begin(), hopping.end(),
        [](const std::shared_ptr<const HoppingModifier>& h) { return h->is_complex(); }
    );

    return complex_potential || complex_hoppings;
}

void HamiltonianModifiers::clear()
{
    onsite.clear();
    hopping.clear();
}
