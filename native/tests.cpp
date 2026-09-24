#include "flight.hpp"
#include <iostream>

void require(bool condition, const std::string& message) {
    if (!condition) flight::fail(message);
}
void near(double actual, double expected, double tolerance, const std::string& name) {
    require(std::abs(actual-expected)<=tolerance, name + ": numerical mismatch");
}
int main() {
#ifndef __wasi__
    try {
#endif
        // Exact constant-acceleration solution exercises the RK integrator independently.
        flight::State initial{0,0,100,2,-3,20};
        auto ballistic=[](double, const flight::State& s) {
            return flight::State{s[3],s[4],s[5],0,0,-flight::gravity};
        };
        auto s=flight::rk4(initial,0,2.5,ballistic);
        near(s[0],5,1e-12,"ballistic east");
        near(s[1],-7.5,1e-12,"ballistic north");
        near(s[2],100+20*2.5-.5*flight::gravity*2.5*2.5,1e-12,"ballistic altitude");
        flight::Config c;
        c.air_density=0; c.elevation=90; c.wind_east=0; c.wind_north=0;
        auto vacuum=flight::simulate(c);
        // Independent Tsiolkovsky solution for constant thrust and mass flow.
        double m0=c.dry_mass+c.propellant_mass, mdot=c.propellant_mass/c.burn_time;
        double ve=c.thrust/mdot;
        double expected_v=ve*std::log(m0/c.dry_mass)-flight::gravity*c.burn_time;
        double expected_z=ve*(c.burn_time-c.dry_mass/mdot*std::log(m0/c.dry_mass))
            -.5*flight::gravity*c.burn_time*c.burn_time;
        bool found=false;
        for (auto& p:vacuum.samples) if (std::abs(p.time-c.burn_time)<1e-8) {
            near(p.state[5],expected_v,1e-8,"vacuum burnout velocity");
            near(p.state[2],expected_z,1e-8,"vacuum burnout altitude"); found=true;
        }
        require(found,"exact burnout boundary missing");
        near(vacuum.apogee,expected_z+expected_v*expected_v/(2*flight::gravity),1e-7,"vacuum apogee");
        double landing=c.burn_time+(expected_v+std::sqrt(expected_v*expected_v+2*flight::gravity*expected_z))/flight::gravity;
        near(vacuum.samples.back().time,landing,1e-8,"ground event");
        c=flight::Config{};
        auto coarse=flight::simulate(c);
        c.time_step=.01;
        auto fine=flight::simulate(c);
        near(coarse.apogee,fine.apogee,1e-5,"step convergence");
        require(coarse.status=="landed","default flight should finish");
        require(coarse.apogee<vacuum.apogee,"drag must reduce apogee");
        double previous=-1;
        for(auto& p:fine.samples) {
            require(p.time>previous,"timestamps must increase"); previous=p.time;
            require(p.state[2]>=0,"below ground sample");
            require(p.mass>=c.dry_mass,"mass below dry mass");
        }
        c.thrust=0;
        require(flight::simulate(c).status=="no_liftoff","zero thrust liftoff");
        c=flight::Config{}; c.thrust=4;
        auto delayed=flight::simulate(c);
        require(delayed.events.front().time>0,"delayed liftoff expected");
        // Regression: an accepted 0.1 s step formerly overestimated burnout
        // velocity by 22.6% as the motor consumed most of the initial mass.
        c=flight::Config{};
        c.dry_mass=.05; c.propellant_mass=.5; c.thrust=100;
        c.burn_time=.1; c.time_step=.1; c.elevation=90;
        c.air_density=0; c.wind_east=0; c.wind_north=0;
        auto rapid=flight::simulate(c);
        mdot=c.propellant_mass/c.burn_time;
        ve=c.thrust/mdot; m0=c.dry_mass+c.propellant_mass;
        expected_v=ve*std::log(m0/c.dry_mass)-flight::gravity*c.burn_time;
        expected_z=ve*(c.burn_time-c.dry_mass/mdot*std::log(m0/c.dry_mass))
            -.5*flight::gravity*c.burn_time*c.burn_time;
        found=false;
        for (const auto& p:rapid.samples) if (std::abs(p.time-c.burn_time)<1e-8) {
            near(p.state[5],expected_v,2e-7,"rapid mass burnout velocity");
            near(p.state[2],expected_z,2e-8,"rapid mass burnout altitude");
            found=true;
        }
        require(found,"rapid mass exact burnout boundary missing");
        c=flight::Config{};c.motor_mode="curve";
        c.thrust_curve={{0,0},{1,20},{2,0}};
        c.validate();flight::Motor motor(c);
        near(motor.impulse,20,1e-12,"triangular impulse");
        near(motor.thrust_at(.5),10,1e-12,"interpolated thrust");
        near(motor.thrust_at(2),0,0,"curve burnout thrust");
        near(motor.mass_at(1),.39,1e-12,"half impulse mass");
        motor.mass_at(1.9);motor.mass_at(.1);
        near(motor.mass_at(1),.39,1e-12,"mass independent of evaluation order");
        c=flight::Config{};c.wind_east=0;c.wind_north=0;
        flight::Sample terminal;
        terminal.mass=c.dry_mass;terminal.state_motion="Descending";
        terminal.effective_cda=c.recovery_area*c.recovery_cd;
        const double cda=terminal.effective_cda+c.drag_coefficient*flight::pi*c.diameter*c.diameter/4;
        terminal.state[5]=-std::sqrt(2*c.dry_mass*flight::gravity/(c.air_density*cda));
        near(flight::forces(c,terminal).az,0,1e-12,"terminal descent force balance");
        c=flight::Config{}; c.time_step=0;
#ifndef __wasi__
        bool rejected=false;
        try {flight::simulate(c);} catch (const std::invalid_argument&) {rejected=true;}
        require(rejected,"invalid step accepted");
#endif
        std::cout << "PASS: ballistic, variable/rapid mass, burnout, apogee, ground, convergence, invariants, liftoff, motor interpolation/impulse, terminal force balance\n";
        return 0;
#ifndef __wasi__
    } catch(const std::exception& e) {std::cerr << "FAIL: " << e.what() << '\n';return 1;}
#endif
}
