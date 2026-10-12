#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include "quant/market/market_state_4d.h"
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <vector>
namespace nb = nanobind;
using namespace nanobind::literals;
using F64 = nb::ndarray<nb::numpy,const double,nb::ndim<1>,nb::c_contig>;
using I64 = nb::ndarray<nb::numpy,const std::int64_t,nb::ndim<1>,nb::c_contig>;
namespace {
nb::ndarray<nb::numpy,double> own(std::vector<double> v) {
  auto owner=std::make_shared<std::vector<double>>(std::move(v));
  const std::size_t shape[]={owner->size()};
  auto* holder=new std::shared_ptr<std::vector<double>>(owner);
  nb::capsule capsule(holder,[](void* p) noexcept { delete static_cast<std::shared_ptr<std::vector<double>>*>(p); });
  return nb::ndarray<nb::numpy,double>(owner->data(),1,shape,capsule);
}
}
NB_MODULE(qros_market_state_4d,m) {
  m.doc()="QROS C++20 dual-clock 4D market-state kernel; contiguous inputs are borrowed without copies.";
  m.def("derive_latency_ms",[](F64 price,F64 volume,I64 event,I64 ingest,double allowed_skew_ms) {
    const auto n=price.shape(0);
    if(volume.shape(0)!=n || event.shape(0)!=n || ingest.shape(0)!=n)
      throw std::invalid_argument("price, volume, event and ingest arrays must have equal length");
    std::vector<quant::market_state_4d::DataPoint4D> points;
    {
      nb::gil_scoped_release release;
      points=quant::market_state_4d::build_points({price.data(),volume.data(),event.data(),ingest.data(),n},allowed_skew_ms);
    }
    std::vector<double> latency; latency.reserve(points.size());
    for(const auto& p:points) latency.push_back(p.latency_ms);
    return own(std::move(latency));
  },"price"_a,"volume"_a,"event_time_ns"_a,"ingest_time_ns"_a,"allowed_clock_skew_ms"_a=1.0);
}
