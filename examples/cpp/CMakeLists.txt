cmake_minimum_required(VERSION 3.21)
project(cal_qt_client LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Qt6 REQUIRED COMPONENTS Core)
add_executable(cal_qt_client main.cpp)
target_link_libraries(cal_qt_client PRIVATE Qt6::Core)

