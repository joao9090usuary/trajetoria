#include "flight.hpp"
#include <sstream>
#include <cstdio>
#include <cerrno>
#include <iomanip>
#include <iostream>
#include <set>

void write_json(std::ostream& out, const flight::Config& c, const flight::Result& r) {
    out << std::setprecision(17) << "{\"config\":{";
    bool first = true;
#define JSON_PARAM(name, value) if (!first) out << ','; first=false; out << "\"" #name "\":" << c.name;
    FLIGHT_PARAMETERS(JSON_PARAM)
#undef JSON_PARAM
    out << ",\"motor_mode\":\"" << c.motor_mode << "\"";
    out << ",\"recovery_enabled\":" << (c.recovery_enabled ? "true" : "false");
    out << ",\"recovery_trigger\":\"" << c.recovery_trigger << "\"";
    out << ",\"thrust_curve\":[";
    for (size_t i=0;i<c.thrust_curve.size();++i) {
        if(i) out << ',';
        out << '[' << c.thrust_curve[i].first << ',' << c.thrust_curve[i].second << ']';
    }
    out << ']';

    const auto& last = r.samples.back();
    out << "},\"status\":\"" << r.status << "\",\"summary\":{\"apogee\":" << r.apogee
        << ",\"max_speed\":" << r.max_speed << ",\"duration\":" << last.time
        << ",\"horizontal_distance\":" << std::hypot(last.state[0], last.state[1])
        << ",\"initial_thrust_to_weight\":" << flight::Motor(c).thrust_at(0)/((c.dry_mass+c.propellant_mass)*flight::gravity)
        << ",\"total_impulse\":" << r.total_impulse << ",\"burn_duration\":" << r.burn_duration
        << ",\"peak_thrust\":" << r.peak_thrust << ",\"mean_thrust\":" << r.total_impulse/r.burn_duration
        << ",\"accepted_steps\":" << r.accepted_steps << ",\"rejected_steps\":" << r.rejected_steps
        << ",\"max_error_ratio\":" << r.max_error_ratio
        << ",\"sample_count\":" << r.samples.size() << "},\"events\":[";
    first=true;
    for (auto& e:r.events) {
        if (!first) out<<','; first=false;
        out << "{\"name\":\"" << e.name << "\",\"time\":" << e.time << ",\"altitude\":" << e.altitude << '}';
    }
    out << "],\"samples\":["; first=true;
    const char* names[] = {"east", "north", "altitude", "velocity_east", "velocity_north", "velocity_up"};
    for (auto& s:r.samples) {
        if (!first) out<<','; first=false;
        out << "{\"time\":" << s.time;
        for (int i=0;i<6;++i) out << ",\"" << names[i] << "\":" << s.state[i];
        const auto f=flight::forces(c,s);
        out << ",\"speed\":" << flight::speed(s.state) << ",\"mass\":" << s.mass << ",\"thrust\":" << s.thrust
            << ",\"effective_cda\":" << s.effective_cda
            << ",\"opening_fraction\":" << s.opening_fraction
            << ",\"density\":" << f.density << ",\"relative_speed\":" << f.relative_speed
            << ",\"drag\":" << f.drag << ",\"weight\":" << f.weight << ",\"acceleration\":" << f.acceleration
            << ",\"acceleration_east\":" << f.ax << ",\"acceleration_north\":" << f.ay << ",\"acceleration_up\":" << f.az
            << ",\"body_drag\":" << f.body_drag << ",\"parachute_drag\":" << f.parachute_drag
            << ",\"dynamic_pressure\":" << f.dynamic_pressure << ",\"along_velocity\":" << f.along_velocity
            << ",\"state_motion\":\"" << s.state_motion << "\""
            << ",\"state_motor\":\"" << s.state_motor << "\""
            << ",\"state_recovery\":\"" << s.state_recovery << "\""
            << '}';
    }
    out << "],\"model\":{\"name\":\"C++17 / RK4 / 3-DOF\",\"version\":\"2.0.0\","
        "\"accuracy\":\"Not experimentally validated\",\"assumptions\":["
        "\"Point mass; fixed thrust direction during free flight\","
        "\"Constant motor: linear mass consumption; curve motor: consumption proportional to impulse\","
        "\"Exponential density; uniform gravity; flat ground; constant wind\","
        "\"Linear parachute CdA inflation; coupled point mass; no opening shock model\"],"
        "\"numerics\":{\"method\":\"RK4 step doubling with Richardson correction\","
        "\"absolute_tolerance\":1e-11,\"relative_tolerance\":1e-12}}}\n";
}

void save_file(const std::string& path, const std::string& content) {
    FILE* file=std::fopen(path.c_str(), "wb");
    if (!file) flight::fail("Cannot open output: " + path);
    const auto count=std::fwrite(content.data(),1,content.size(),file);
    const auto closed=std::fclose(file);
    if (count!=content.size() || closed!=0) flight::fail("Cannot write output: " + path);
}

int main(int argc, char** argv) {
#ifndef __wasi__
    try {
#endif
        flight::Config config;
        std::string json_path, csv_path;
        bool json_stdout=false;
        bool use_stdin=false;
        for (int i=1;i<argc;++i) {
            std::string key=argv[i];
            if (key=="--help") {
                std::cout << "Trajetoria C++17 | SI units | educational research prototype\n"
                    "flight_cli [--stdin] [--json file] [--csv file] [--json-stdout]\n";
                return 0;
            }
            if (key=="--json-stdout") {json_stdout=true;continue;}
            if (key=="--stdin") {use_stdin=true;continue;}
            if (++i>=argc) flight::fail("Missing value for " + key);
            if (key=="--json") json_path=argv[i];
            else if (key=="--csv") csv_path=argv[i];
            else {
                if (key.rfind("--",0)!=0) flight::fail("Expected --parameter");
                char* end=nullptr;
                errno=0;
                double number=std::strtod(argv[i],&end);
                if (end==argv[i] || *end || errno==ERANGE) flight::fail("Invalid number: " + std::string(argv[i]));
                config.set(key.substr(2),number);
            }
        }

        if (use_stdin) {
            std::string key;
            std::set<std::string> seen;
            while (std::cin >> key) {
                if(!seen.insert(key).second) flight::fail("Duplicate parameter: " + key);
                if (key == "thrust_curve") {
                    int count;
                    if (!(std::cin >> count)) flight::fail("Expected count for thrust_curve");
                    if(count<0||count>10000) flight::fail("Invalid curve point count");
                    config.thrust_curve.clear();
                    for (int i=0; i<count; ++i) {
                        double t, v;
                        if (!(std::cin >> t >> v)) flight::fail("Expected pair for thrust_curve");
                        config.thrust_curve.push_back({t, v});
                    }
                } else if (key == "motor_mode" || key == "recovery_trigger") {
                    std::string val;
                    if (!(std::cin >> val)) flight::fail("Expected string for " + key);
                    config.set_string(key, val);
                } else if (key == "recovery_enabled") {
                    int val;
                    if (!(std::cin >> val)) flight::fail("Expected int for recovery_enabled");
                    if(val!=0&&val!=1) flight::fail("recovery_enabled must be 0 or 1");
                    config.recovery_enabled = (val != 0);
                } else {
                    double val;
                    if (!(std::cin >> val)) flight::fail("Expected number for " + key);
                    config.set(key, val);
                }
            }
        }

        auto result=flight::simulate(config);

        if (!json_path.empty()) {
            std::ostringstream out;
            write_json(out,config,result);
            save_file(json_path,out.str());
        }
        if (!csv_path.empty()) {
            std::ostringstream out;
            out << std::setprecision(17) << "time,east,north,altitude,velocity_east,velocity_north,velocity_up,speed,mass,thrust,density,relative_speed,drag,weight,acceleration,effective_cda,opening_fraction,acceleration_east,acceleration_north,acceleration_up,body_drag,parachute_drag,dynamic_pressure,along_velocity,state_motion,state_motor,state_recovery\n";
            for (auto& s:result.samples) {
                out<<s.time;
                for (double v:s.state) out<<','<<v;
                const auto f=flight::forces(config,s);
                out<<','<<flight::speed(s.state)<<','<<s.mass<<','<<s.thrust<<','<<f.density<<','<<f.relative_speed<<','<<f.drag<<','<<f.weight<<','<<f.acceleration
                   <<','<<s.effective_cda<<','<<s.opening_fraction<<','<<f.ax<<','<<f.ay<<','<<f.az
                   <<','<<f.body_drag<<','<<f.parachute_drag<<','<<f.dynamic_pressure<<','<<f.along_velocity
                   <<','<<s.state_motion<<','<<s.state_motor<<','<<s.state_recovery<<'\n';
            }
            save_file(csv_path,out.str());
        }
        if (json_stdout) write_json(std::cout,config,result);
        else std::cout << std::fixed << std::setprecision(6)
            << "TRAJETORIA | C++17 | " << result.status << "\nApogee: " << result.apogee
            << " m\nPeak speed (sampled): " << result.max_speed << " m/s\nDuration: "
            << (result.samples.empty() ? 0 : result.samples.back().time) << " s\nExperimental accuracy: not established.\n";
        return 0;
#ifndef __wasi__
    } catch (const std::exception& e) {std::cerr << "Error: " << e.what() << '\n'; return 1;}
#endif
}
