#include <array>
#include <vector>
#include <type_traits>

template<typename T, std::size_t N>
void carefulResize(std::array<T, N>& arr, std::size_t size) {}

template<typename T>
void carefulResize(std::vector<T>& vec, std::size_t size) {
    vec.resize(size);
}

#ifdef ROS2
#include <rosidl_runtime_cpp/bounded_vector.hpp>
template<typename T, std::size_t N>
void carefulResize(rosidl_runtime_cpp::BoundedVector<T, N>& bounded_vec, std::size_t size) {
    bounded_vec.resize(size);
}
#endif