#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace flight {
[[noreturn]] inline void fail(const std::string& message) {
#ifdef __wasi__
    std::cerr << "Error: " << message << '\n';
    std::exit(1);
#else
    throw std::invalid_argument(message);
#endif
}
constexpr double gravity = 9.80665;
constexpr double pi = 3.14159265358979323846;
using State = std::array<double, 6>;
#define FLIGHT_PARAMETERS(X) \
 X(dry_mass, .35) X(propellant_mass, .08) X(thrust, 12) X(burn_time, 2) \
 X(diameter, .05) X(drag_coefficient, .55) X(elevation, 85) X(azimuth, 30) \
 X(wind_east, 2) X(wind_north, .5) X(air_density, 1.225) X(time_step, .02) \
 X(max_time, 120) X(recovery_delay, 0) X(recovery_inflation, 1) \
 X(recovery_area, .3) X(recovery_cd, 1.5) X(recovery_altitude, 50) X(recovery_time, 5)

struct Config {
#define FIELD(name, value) double name = value;
    FLIGHT_PARAMETERS(FIELD)
#undef FIELD
    std::string motor_mode = "constant", recovery_trigger = "apogee";
    std::vector<std::pair<double, double>> thrust_curve;
    bool recovery_enabled = false;
    void validate() const {
        auto bound=[](double v,double lo,double hi,const char* name) {
            if(!std::isfinite(v)||v<lo||v>hi) fail(std::string("Invalid parameter: ")+name);
        };
#define B(name, lo, hi) bound(name,lo,hi,#name)
        B(dry_mass,.01,100); B(propellant_mass,.001,100);
        B(thrust,0,10000); B(burn_time,.01,100); B(diameter,.01,1);
        B(drag_coefficient,0,2); B(elevation,60,90); B(azimuth,0,360);
        B(wind_east,-30,30); B(wind_north,-30,30); B(air_density,0,1.5);
        B(time_step,.001,.1); B(max_time,10,1000);
        B(recovery_delay,0,60); B(recovery_inflation,.01,30);
        B(recovery_area,.001,20); B(recovery_cd,.1,3);
        B(recovery_altitude,0,10000); B(recovery_time,0,180);
#undef B
        if(motor_mode!="constant"&&motor_mode!="curve") fail("Invalid motor_mode");
        if(recovery_trigger!="apogee"&&recovery_trigger!="time"&&recovery_trigger!="altitude") fail("Invalid recovery_trigger");
        if(motor_mode=="constant"&&!thrust_curve.empty()) fail("Constant motor must not contain a curve");
        if(motor_mode=="curve") {
            if(thrust_curve.size()<2||thrust_curve.size()>10000) fail("Curve requires 2 to 10000 points");
            double prev=-1, impulse=0;
            for(size_t i=0;i<thrust_curve.size();++i) {
                const auto p=thrust_curve[i];
                bound(p.first,0,100,"curve time"); bound(p.second,0,10000,"curve thrust");
                if(p.first<=prev) fail("Curve times must increase strictly");
                if(i) impulse+=(p.first-prev)*(p.second+thrust_curve[i-1].second)/2;
                prev=p.first;
            }
            if(thrust_curve.front().first!=0||thrust_curve.back().second!=0||
               thrust_curve.back().first<.01||impulse<=0) fail("Curve must start at time 0, end at zero thrust, and have positive impulse");
        }
    }
    void set(const std::string& key,double value) {
#define SET(name, initial) if(key==#name){name=value;return;}
        FLIGHT_PARAMETERS(SET)
#undef SET
        fail("Unknown numeric parameter: "+key);
    }
    void set_string(const std::string& key,const std::string& value) {
        if(key=="motor_mode") motor_mode=value;
        else if(key=="recovery_trigger") recovery_trigger=value;
        else fail("Unknown string parameter: "+key);
    }
};

// Pure evaluation: rejected RK stages and event searches never consume mass.
struct Motor {
    const Config& c;
    std::vector<double> integrals;
    double duration, impulse, peak;
    explicit Motor(const Config& config):c(config),duration(c.burn_time),impulse(c.thrust*c.burn_time),peak(c.thrust) {
        if(c.motor_mode=="curve") {
            duration=c.thrust_curve.back().first; impulse=0; peak=0;
            integrals.push_back(0);
            for(size_t i=0;i<c.thrust_curve.size();++i) {
                peak=std::max(peak,c.thrust_curve[i].second);
                if(i) {
                    impulse+=(c.thrust_curve[i].first-c.thrust_curve[i-1].first)*
                        (c.thrust_curve[i].second+c.thrust_curve[i-1].second)/2;
                    integrals.push_back(impulse);
                }
            }
        }
    }
    size_t segment(double t) const {
        auto it=std::upper_bound(c.thrust_curve.begin(),c.thrust_curve.end(),t,
            [](double x,const auto& p){return x<p.first;});
        return std::min(c.thrust_curve.size()-2,static_cast<size_t>(it-c.thrust_curve.begin()-1));
    }
    double thrust_at(double t) const {
        if(t<0||t>=duration) return 0;
        if(c.motor_mode=="constant") return c.thrust;
        const auto i=segment(t);
        const auto a=c.thrust_curve[i],b=c.thrust_curve[i+1];
        return a.second+(b.second-a.second)*(t-a.first)/(b.first-a.first);
    }
    double impulse_at(double t) const {
        t=std::clamp(t,0.,duration);
        if(c.motor_mode=="constant") return c.thrust*t;
        if(t>=duration) return impulse;
        const auto i=segment(t); const auto a=c.thrust_curve[i];
        return integrals[i]+(a.second+thrust_at(t))*(t-a.first)/2;
    }
    double mass_at(double t) const {
        double consumed=c.motor_mode=="constant"?std::clamp(t/duration,0.,1.):impulse_at(t)/impulse;
        return c.dry_mass+c.propellant_mass*(1-consumed);
    }
    double liftoff() const {
        const double vertical=std::sin(c.elevation*pi/180);
        auto margin=[&](double t) {
            double thrust=(c.motor_mode=="constant"&&t==duration)?c.thrust:thrust_at(t);
            return thrust*vertical-mass_at(t)*gravity;
        };
        std::vector<double> times{0,duration};
        if(c.motor_mode=="curve") {
            times.clear();
            for(size_t i=0;i<c.thrust_curve.size();++i) {
                const auto a=c.thrust_curve[i]; times.push_back(a.first);
                if(i+1<c.thrust_curve.size()) {
                    const auto b=c.thrust_curve[i+1];
                    const double slope=(b.second-a.second)/(b.first-a.first);
                    const double coefficient=gravity*c.propellant_mass/impulse;
                    if(slope!=0) {
                        const double x=-(slope*vertical+coefficient*a.second)/(coefficient*slope);
                        if(x>0&&x<b.first-a.first) times.push_back(a.first+x);
                    }
                }
            }
            std::sort(times.begin(),times.end());
        }
        if(margin(0)>0) return 0;
        for(size_t i=1;i<times.size();++i) if(margin(times[i])>0) {
            double lo=times[i-1],hi=times[i];
            for(int n=0;n<60;++n) {double mid=(lo+hi)/2;if(margin(mid)>0)hi=mid;else lo=mid;}
            return hi<duration?hi:std::numeric_limits<double>::infinity();
        }
        return std::numeric_limits<double>::infinity();
    }
};

struct Sample {
    double time=0;
    State state{};
    double mass=0,thrust=0,effective_cda=0;
    std::string state_motion="Supported",state_motor="Burning",state_recovery="None";
    double opening_fraction=0;
};
struct Event {std::string name;double time,altitude;};
struct Result {
    std::vector<Sample> samples;
    std::vector<Event> events;
    std::string status="time_limit";
    double apogee=0,max_speed=0,total_impulse=0,burn_duration=0,peak_thrust=0,max_error_ratio=0;
    size_t accepted_steps=0,rejected_steps=0;
};
inline double speed(const State& s){return std::hypot(s[3],s[4],s[5]);}
struct Forces {
    double density,relative_speed,drag,weight,acceleration,ax,ay,az;
    double body_drag,parachute_drag,dynamic_pressure,along_velocity;
};
inline Forces forces(const Config& c,const Sample& s) {
    double rho=c.air_density*std::exp(-std::max(0.,s.state[2])/8500);
    double vx=s.state[3]-c.wind_east,vy=s.state[4]-c.wind_north,vz=s.state[5];
    double rel=std::hypot(vx,vy,vz),q=.5*rho*rel*rel;
    double body=q*c.drag_coefficient*pi*c.diameter*c.diameter/4,chute=q*s.effective_cda;
    double drag=body+chute,f=rel>0?drag/rel:0;
    double el=c.elevation*pi/180,az=c.azimuth*pi/180;
    double ax=(s.thrust*std::cos(el)*std::sin(az)-f*vx)/s.mass;
    double ay=(s.thrust*std::cos(el)*std::cos(az)-f*vy)/s.mass;
    double up=(s.thrust*std::sin(el)-f*vz)/s.mass-gravity;
    if(s.state_motion=="Supported") ax=ay=up=0;
    double v=speed(s.state),along=v>0?(ax*s.state[3]+ay*s.state[4]+up*s.state[5])/v:0;
    return {rho,rel,drag,s.mass*gravity,std::hypot(ax,ay,up),ax,ay,up,body,chute,q,along};
}
template<class Derivative>
State rk4(const State& s,double t,double h,const Derivative& derivative) {
    const auto k1=derivative(t,s); State tmp{};
    for(int i=0;i<6;++i) tmp[i]=s[i]+h*k1[i]/2;
    const auto k2=derivative(t+h/2,tmp);
    for(int i=0;i<6;++i) tmp[i]=s[i]+h*k2[i]/2;
    const auto k3=derivative(t+h/2,tmp);
    for(int i=0;i<6;++i) tmp[i]=s[i]+h*k3[i];
    const auto k4=derivative(t+h,tmp);
    for(int i=0;i<6;++i) tmp[i]=s[i]+h*(k1[i]+2*k2[i]+2*k3[i]+k4[i])/6;
    return tmp;
}

inline Result simulate(const Config& c) {
    c.validate(); const Motor motor(c);
    Result r; r.total_impulse=motor.impulse;r.burn_duration=motor.duration;r.peak_thrust=motor.peak;
    const double infinity=std::numeric_limits<double>::infinity();
    const double lift=motor.liftoff();
    double time=0,trigger=infinity,ejection=infinity;
    bool airborne=false,apogee=false,burnout=false,ejected=false,opened=false;
    State state{};
    auto sample=[&](double t,const State& s) {
        Sample p;
        p.time=t;p.state=s;p.mass=motor.mass_at(t);p.thrust=motor.thrust_at(t);
        p.state_motion=airborne?(s[5]<0?"Descending":"Ascending"):"Supported";
        p.state_motor=t<motor.duration?"Burning":"Burnout";
        p.state_recovery=c.recovery_enabled?"Stowed":"None";
        if(t>=trigger) p.state_recovery="Armed";
        if(t>=ejection) {
            p.opening_fraction=std::clamp((t-ejection)/c.recovery_inflation,0.,1.);
            if(t>=ejection+c.recovery_inflation) p.opening_fraction=1;
            p.effective_cda=p.opening_fraction*c.recovery_cd*c.recovery_area;
            p.state_recovery=p.opening_fraction>=1?"FullyOpen":"Inflating";
        }
        return p;
    };
    auto append=[&](Sample p) {
        r.apogee=std::max(r.apogee,p.state[2]);r.max_speed=std::max(r.max_speed,speed(p.state));
        if(!r.samples.empty()&&p.time==r.samples.back().time) r.samples.back()=p;
        else r.samples.push_back(p);
        if(r.samples.size()>300000) fail("Sample budget exceeded");
    };
    auto event=[&](const std::string& name){r.events.push_back({name,time,state[2]});};
    auto updates=[&]() {
        if(!burnout&&time>=motor.duration) {burnout=true;event("burnout");}
        if(c.recovery_enabled&&!std::isfinite(trigger)&&airborne) {
            bool ready=(c.recovery_trigger=="apogee"&&apogee)||
                (c.recovery_trigger=="time"&&time>=c.recovery_time)||
                (c.recovery_trigger=="altitude"&&apogee&&state[5]<=1e-8&&state[2]<=c.recovery_altitude+1e-9);
            if(ready) {trigger=time;ejection=time+c.recovery_delay;event("recovery_trigger");}
        }
        if(!ejected&&time>=ejection) {ejected=true;event("ejection");event("inflation_start");}
        if(!opened&&time>=ejection+c.recovery_inflation) {opened=true;event("parachute_open");}
    };
    append(sample(0,state));
    if(!std::isfinite(lift)) {r.status="no_liftoff";return r;}
    if(lift>c.max_time) {time=c.max_time;append(sample(time,state));return r;}
    time=lift;airborne=true;event("liftoff");updates();append(sample(time,state));
    double next_step=c.time_step;
    size_t trials=0;
    while(time<c.max_time) {
        if(++trials>1000000) fail("Integration budget exceeded");
        double boundary=c.max_time;
        auto limit=[&](double t){if(t>time)boundary=std::min(boundary,t);};
        limit(motor.duration);
        if(c.motor_mode=="curve") {
            auto it=std::upper_bound(c.thrust_curve.begin(),c.thrust_curve.end(),time,
                [](double t,const auto& p){return t<p.first;});
            if(it!=c.thrust_curve.end()) limit(it->first);
        }
        if(c.recovery_enabled&&c.recovery_trigger=="time"&&!std::isfinite(trigger)) limit(c.recovery_time);
        limit(ejection);limit(ejection+c.recovery_inflation);
        double h=std::min(next_step,boundary-time);
        // The burning interval is left-continuous for RK endpoint evaluations;
        // exported burnout samples are right-continuous, with thrust equal to zero.
        auto derivative=[&](double t,const State& s) {
            auto p=sample(t,s);
            if(c.motor_mode=="constant"&&time<motor.duration&&t>=motor.duration) p.thrust=c.thrust;
            const auto f=forces(c,p);
            return State{s[3],s[4],s[5],f.ax,f.ay,f.az};
        };
        auto advance=[&](double dt,double* ratio) {
            const auto whole=rk4(state,time,dt,derivative);
            const auto half=rk4(state,time,dt/2,derivative);
            auto finer=rk4(half,time+dt/2,dt/2,derivative);
            double error=0;
            for(int i=0;i<6;++i) {
                const double correction=(finer[i]-whole[i])/15;
                const double scale=1e-11+1e-12*std::max(std::abs(state[i]),std::abs(finer[i]));
                error=std::max(error,std::abs(correction)/scale);
                finer[i]+=correction;
                if(!std::isfinite(finer[i])) fail("Numerical instability");
            }
            if(ratio) *ratio=error;
            return finer;
        };
        State next{}; double error=0;
        while(true) {
            if(h<=0||time+h==time) fail("Integration cannot advance");
            next=advance(h,&error);
            if(error<=1) break;
            ++r.rejected_steps;
            h*=std::clamp(.9*std::pow(error,-.2),.1,.5);
            if(h<1e-12||++trials>1000000) fail("Requested numerical precision cannot be reached");
        }
        r.max_error_ratio=std::max(r.max_error_ratio,error);
        next_step=std::min(c.time_step,h*std::clamp(error>0?.9*std::pow(error,-.2):2.,.5,2.));
        auto root=[&](int component,double target) {
            double lo=0,hi=h;
            for(int n=0;n<45;++n) {
                const double mid=(lo+hi)/2;
                if(advance(mid,nullptr)[component]>target)lo=mid;else hi=mid;
            }
            return (lo+hi)/2;
        };
        bool apex_event=false,altitude_event=false,ground_event=false;
        double event_h=h;
        if(!apogee&&state[5]>0&&next[5]<=0) {event_h=root(5,0);apex_event=true;}
        if(c.recovery_enabled&&c.recovery_trigger=="altitude"&&!std::isfinite(trigger)&&
           apogee&&state[2]>c.recovery_altitude&&next[2]<=c.recovery_altitude) {
            const double x=root(2,c.recovery_altitude);
            if(x<event_h) {event_h=x;apex_event=false;altitude_event=true;}
        }
        if(next[2]<0) {
            const double x=root(2,0);
            if(x<=event_h) {event_h=x;apex_event=false;altitude_event=false;ground_event=true;}
        }
        if(apex_event||altitude_event||ground_event) {h=event_h;next=advance(h,nullptr);}
        const double end=time+h;
        time=(std::abs(end-boundary)<1e-12&&!apex_event&&!altitude_event&&!ground_event)?boundary:end;
        state=next;
        if(apex_event){state[5]=0;apogee=true;event("apogee");}
        if(altitude_event) state[2]=c.recovery_altitude;
        ++r.accepted_steps;
        if(ground_event) {
            state[2]=0;r.status="landed";event("ground_contact");
            auto p=sample(time,state);p.state_motion="Landed";append(p);break;
        }
        updates();append(sample(time,state));
    }
    return r;
}
} // namespace flight
