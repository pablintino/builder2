from compilers_support import get_gcc_wellknown_paths


def test_test():
    paths = get_gcc_wellknown_paths("/opt/compilers/gcc-10.3.0")
    print(paths)
