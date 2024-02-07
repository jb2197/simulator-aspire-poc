from __future__ import annotations

import collections
import math
import os
import random
import itertools as it
from abc import ABC
from collections import defaultdict
from itertools import product, combinations

import gurobipy as gp
import numpy as np
from docplex.mp.model import Model
from gurobipy import GRB
from monty.json import MSONable
from pydantic import BaseModel
from ortools.sat.python import cp_model
from ortools.linear_solver import pywraplp
from utils import get_big_m_value

# from reaction_network.schema.lv2 import BenchTopLv2, OperationType

# os.environ["GRB_LICENSE_FILE"] = "/home/qai/local/gurobi_lic/gurobi.lic"


def get_gurobi_var_index(
    var_name: str,
    var_header: str,
) -> int | list[int]:
    assert var_name.startswith(var_header)
    assert var_name.endswith("]")
    stripped_index_string = var_name[len(var_header) :].lstrip("[").rstrip("]")
    n_index = var_name.count(",") + 1
    assert n_index >= 1
    if n_index == 1:
        i = int(stripped_index_string)
    else:
        i = stripped_index_string.split(",")
        i = [int(ii) for ii in i]
    return i


class SolvedOperation(BaseModel):
    id: str
    assigned_to: str
    start_time: float
    end_time: float


class FjsOutput(BaseModel):
    solved_operations: list[SolvedOperation]
    makespan: float

    @property
    def machine_timetable(self):
        timetable = defaultdict(list)
        for op in self.solved_operations:
            timetable[op.assigned_to].append((op.start_time, op.end_time))
        return timetable


def get_dummy_time_est(operation_type: OperationType):
    # in seconds
    if operation_type in [
        OperationType.OPERATION_LOADING,
        OperationType.OPERATION_UNLOADING,
        OperationType.OPERATION_RELOADING,
    ]:
        base_cost = 120
    elif operation_type in [OperationType.OPERATION_HEATING]:
        base_cost = 30 * 60
    elif operation_type in [OperationType.OPERATION_ADDITION_LIQUID]:
        base_cost = 2 * 60
    elif operation_type in [OperationType.OPERATION_ADDITION_SOLID]:
        base_cost = 5 * 60
    elif operation_type in [OperationType.OPERATION_PURIFICATION]:
        base_cost = 45 * 60
    else:
        raise NotImplementedError
    return random.uniform(base_cost * 0.8, base_cost * 1.2)


class _FJS(MSONable, ABC):
    def __init__(
        self,
        operations: list[str],
        machines: list[str],
        precedence: dict[str, list[str]],
        time_estimates: dict[str, dict[str, float]] | None,
        model_string: str | None = None,
    ):
        """
        # TODO implement io (loading lp file)

        :param operations: the list of operation ids
        :param machines: the list of machine ids
        :param precedence: p[i] = a list of j where j precedes i
        :param time_estimates: t[i][k] is the time cost of operation i on machine k, inf if i cannot be done by k
        :param model_string: dumped cplex model string (lp file)
        """
        self.model_string = model_string
        self.time_estimates = time_estimates
        self.precedence = precedence
        self.machines = machines
        self.operations = operations
        self._model = None

    def get_machine_ids_can_process(self, operation_id: str) -> list[str]:
        assert operation_id in self.operations
        amids = []
        for machine_id in self.machines:
            if not math.isinf(self.time_estimates[operation_id][machine_id]):
                amids.append(machine_id)
        return amids

    @classmethod
    def from_bench_top(
        cls, bench_top: BenchTopLv2, time_estimates: dict[str, dict[str, float]] = None
    ):
        p = dict()
        for operation_id, operation in bench_top.operation_dict.items():
            p[operation_id] = operation.precedents

        machines = []
        for v in bench_top.operation_type_device_mapping.values():
            machines += v
        machines = sorted(set(machines))
        if time_estimates is None:
            # generate dummy time estimate
            time_est = defaultdict(dict)
            random.seed(42)
            for operation_id, operation in bench_top.operation_dict.items():
                can_be_processed_by = bench_top.operation_type_device_mapping[
                    operation.type
                ]
                for mid in machines:
                    if mid in can_be_processed_by:
                        time_est[operation_id][mid] = get_dummy_time_est(operation.type)
                    else:
                        time_est[operation_id][mid] = math.inf
        else:
            time_est = time_estimates
        return cls(
            operations=sorted(bench_top.operation_dict.keys()),
            machines=machines,
            precedence=p,
            time_estimates=time_est,
        )


class FJS1(_FJS):
    """
    following the formulation in:
    Kasapidis 2021, Flexible Job Shop Scheduling Problems with Arbitrary Precedence Graphs, sec 2.2
    """

    @property
    def model(self) -> Model | gp.Model | None:
        return self._model

    def get_params(self):
        i_dict = {i: oid for i, oid in enumerate(self.operations)}
        i_dict_rev = {oid: i for i, oid in enumerate(self.operations)}
        k_dict = {k: mid for k, mid in enumerate(self.machines)}

        p_i_k = defaultdict(dict)
        for i, operation_id in i_dict.items():
            for k, machine_id in k_dict.items():
                te = self.time_estimates[operation_id][machine_id]
                if not math.isinf(te):
                    p_i_k[i][k] = te
        p_i_k: dict[
            int, dict[int, float]
        ]  # processing time of operation i on machine k

        pj = dict()
        for i, operation_id in i_dict.items():
            predecessors = self.precedence[operation_id]
            pj[i] = [i_dict_rev[predecessor] for predecessor in predecessors]
        pj: dict[int, list[int]]

        # estimate curl M
        # "a valid upper bound for M can be calculated as ∑ i∈Ω maxk∈Mi pi,k."
        big_m = 0
        for i in i_dict:
            big_m += max(p_i_k[i].values())

        return i_dict, i_dict_rev, k_dict, p_i_k, pj, big_m

    def build_model_cplex(self):
        from docplex.mp.model import Model
        from docplex.mp.dvar import Var

        i_dict, i_dict_rev, k_dict, p_i_k, pj, big_m = self.get_params()

        model = Model(name="FJS1")
        var_c_max = model.continuous_var(name="C_max", lb=0, ub=model.infinity)

        vars_x_i_j_k = model.binary_var_cube(
            len(i_dict), len(i_dict), len(k_dict), name="X"
        )  # eq 15
        vars_x_i_j_k: dict[tuple[int, int, int], Var]

        vars_y_i_k = model.binary_var_matrix(
            len(i_dict), len(k_dict), name="Y"
        )  # eq 16
        vars_y_i_k: dict[tuple[int, int], Var]

        vars_c_i = model.continuous_var_dict(
            len(i_dict), lb=0, ub=model.infinity, name="C"
        )
        vars_c_i: dict[int, Var]

        # eq 9 and 10
        for i, operation_id in i_dict.items():
            available_ks = sorted(p_i_k[i].keys())
            model.add_constraint(
                sum([vars_y_i_k[(i, k)] for k in available_ks]) == 1,
                ctname=f"eq 9: i={i}",
            )
            for j in pj[i]:
                model.add_constraint(
                    vars_c_i[i]
                    >= vars_c_i[j]
                    + sum([vars_y_i_k[(i, k)] * p_i_k[i][k] for k in available_ks]),
                    ctname=f"eq 10: i={i} j={j}",
                )

        # eq 11 and eq 12
        for i, operation_id_i in i_dict.items():
            for j, operation_id_j in i_dict.items():
                if i == j:
                    continue
                k_list = sorted(set(p_i_k[i].keys()).intersection(set(p_i_k[j].keys())))
                for k in k_list:
                    model.add_constraint(
                        vars_c_i[i]
                        >= vars_c_i[j]
                        + p_i_k[i][k]
                        - big_m
                        * (
                            2
                            + vars_x_i_j_k[(i, j, k)]
                            - vars_y_i_k[(i, k)]
                            - vars_y_i_k[(j, k)]
                        ),
                        ctname=f"eq 11: i={i} j={j} k={k}",
                    )

                    model.add_constraint(
                        vars_c_i[j]
                        >= vars_c_i[i]
                        + p_i_k[j][k]
                        - big_m
                        * (
                            3
                            - vars_x_i_j_k[(i, j, k)]
                            - vars_y_i_k[(i, k)]
                            - vars_y_i_k[(j, k)]
                        ),
                        ctname=f"eq 12: i={i} j={j} k={k}",
                    )

        # eq 14
        model.add_constraints([var_c_max >= C_i for C_i in vars_c_i], names="eq 14")
        self.model_string = model.export_to_string()
        self._model = model
        return model

    def build_model_gurobi(self):
        env = gp.Env(
            empty=True
        )  # TODO this arrangement doesn't really suppress stdout...
        env.setParam("OutputFlag", 0)
        env.setParam("LogToConsole", 0)
        env.start()

        i_dict, i_dict_rev, k_dict, p_i_k, pj, big_m = self.get_params()

        model = gp.Model(self.__class__.__name__)

        var_c_max = model.addVar(
            name="C_max", lb=1e-5, ub=float("inf"), vtype=GRB.CONTINUOUS
        )

        vars_x_i_j_k = model.addVars(
            len(i_dict), len(i_dict), len(k_dict), name="X", vtype=GRB.BINARY
        )  # eq 15
        vars_x_i_j_k: gp.tupledict[tuple[int, int, int], gp.Var]

        vars_y_i_k = model.addVars(
            len(i_dict), len(k_dict), name="Y", vtype=GRB.BINARY
        )  # eq 16
        vars_y_i_k: gp.tupledict[tuple[int, int], gp.Var]

        vars_c_i = model.addVars(
            len(i_dict), name="C", lb=0, ub=float("inf"), vtype=GRB.CONTINUOUS
        )
        vars_c_i: gp.tupledict[int, gp.Var]

        # eq 9 and 10
        for i, operation_id in i_dict.items():
            available_ks = sorted(p_i_k[i].keys())
            model.addConstr(
                sum([vars_y_i_k[(i, k)] for k in available_ks]) == 1,
                name=f"eq 9: i={i}",
            )
            for j in pj[i]:
                model.addConstr(
                    vars_c_i[i]
                    >= vars_c_i[j]
                    + sum([vars_y_i_k[(i, k)] * p_i_k[i][k] for k in available_ks]),
                    name=f"eq 10: i={i} j={j}",
                )

        # eq 11 and eq 12
        for i, operation_id_i in i_dict.items():
            for j, operation_id_j in i_dict.items():
                if i == j:
                    continue
                k_list = sorted(set(p_i_k[i].keys()).intersection(set(p_i_k[j].keys())))
                for k in k_list:
                    model.addConstr(
                        vars_c_i[i]
                        >= vars_c_i[j]
                        + p_i_k[i][k]
                        - big_m
                        * (
                            2
                            + vars_x_i_j_k[(i, j, k)]
                            - vars_y_i_k[(i, k)]
                            - vars_y_i_k[(j, k)]
                        ),
                        name=f"eq 11: i={i} j={j} k={k}",
                    )

                    model.addConstr(
                        vars_c_i[j]
                        >= vars_c_i[i]
                        + p_i_k[j][k]
                        - big_m
                        * (
                            3
                            - vars_x_i_j_k[(i, j, k)]
                            - vars_y_i_k[(i, k)]
                            - vars_y_i_k[(j, k)]
                        ),
                        name=f"eq 12: i={i} j={j} k={k}",
                    )

        # eq 14
        for i, c_i in vars_c_i.items():
            model.addConstr(var_c_max >= c_i, name=f"eq 14: i={i}")

        model.setObjective(var_c_max, GRB.MINIMIZE)
        self.model_string = model.__str__()
        self._model = model
        env.close()

    def solve_cplex(self):
        assert self.model is not None
        self.model.solve()
        # TODO export to FjsOutput

    def solve_gurobi(self):
        assert self.model is not None
        self.model.optimize()

        i_dict, i_dict_rev, k_dict, p_i_k, pj, big_m = self.get_params()

        k_dict_rev = {v: k for k, v in k_dict.items()}

        start_times = dict()
        assignments = dict()

        makespan = None

        self.model.solution

        for v in self.model.getVars():
            if v.VarName.startswith("C") and v.VarName.endswith("]"):
                i = get_gurobi_var_index(v.VarName, "C")
                operation_id = i_dict[i]
                start_times[operation_id] = v.X
            elif v.VarName.startswith("Y") and v.VarName.endswith("]"):
                i, k = get_gurobi_var_index(v.VarName, "Y")
                operation_id = i_dict[i]
                machine_id = k_dict[k]
                if v.X == 1:
                    assignments[operation_id] = machine_id
            elif v.VarName == "C_max":
                makespan = v.X
        end_times = dict()
        for operation_id, st in start_times.items():
            machine_id = assignments[operation_id]
            et = st + p_i_k[i_dict_rev[operation_id]][k_dict_rev[machine_id]]
            end_times[operation_id] = et
        assert makespan == self.model.ObjVal
        solved_operations = []
        for operation_id in start_times:
            solved_operation = SolvedOperation(
                id=operation_id,
                assigned_to=assignments[operation_id],
                start_time=start_times[operation_id],
                end_time=end_times[operation_id],
            )
            solved_operations.append(solved_operation)
        return FjsOutput(
            solved_operations=solved_operations,
            makespan=makespan,
        )


class FJS2:
    """
    Implementation of the mixed integer programming formulation in:
    Boyer, V., Vallikavungal, J., Rodríguez, X. C., & Salazar-Aguilar, M. A. (2021). The generalized flexible job shop scheduling problem. Computers & Industrial Engineering, 160, 107542.
    """

    def __init__(
        self,
        operations: list[str],
        machines: list[str],
        para_p: np.ndarray,
        para_a: np.ndarray,
        para_w: np.ndarray,
        para_h: np.ndarray,
        para_delta: np.ndarray,
        para_mach_capacity: list[int] | np.ndarray,
        para_lmin: np.ndarray,
        para_lmax: np.ndarray,
        precedence: dict[str, list[str]],
        model_string: str | None = None,
        num_workers: int = None,
        inf_milp: float = 1.0e7,
        shift_durations: float|int = None,
        operations_subset_indices: list[int] = None,
        big_m: float | int = None,
        # big_m=1.0e6,
        matrix_variables=True,
        verbose: bool = True,
    ):
        self.num_workers = num_workers
        self.matrix_variables = matrix_variables
        # self.big_m = get_m_value(
        #     para_p=para_p, para_h=para_h, para_lmin=para_lmin, para_a=para_a
        # )

        para_lmin[para_lmin == -np.inf] = -inf_milp
        para_lmin[para_lmin == np.inf] = inf_milp
        para_lmax[para_lmax == np.inf] = inf_milp
        para_lmax[para_lmax == -np.inf] = -inf_milp
        para_p[para_p == np.inf] = inf_milp
        para_p[para_p == -np.inf] = -inf_milp
        para_w[para_w == np.inf] = inf_milp
        para_w[para_w == -np.inf] = -inf_milp
        para_a[para_a == np.inf] = inf_milp
        para_a[para_a == -np.inf] = -inf_milp

        self.inf_milp = inf_milp

        # self.operations = operations
        # self.machines = machines
        # if operations is a list, turn it into a dictionary
        if isinstance(operations, list):
            operations = {i: operations[i] for i in range(len(operations))}
        if isinstance(machines, list):
            machines = {i: machines[i] for i in range(len(machines))}

        self.operations = operations
        self.machines = machines

        self.precedence = precedence
        # self.time_estimates = None
        self.model_string = model_string

        self.para_p = para_p
        self.para_a = para_a
        self.para_w = para_w
        self.para_delta = para_delta
        self.para_lmin = para_lmin
        self.para_lmax = para_lmax
        self.para_h = para_h
        self.para_mach_capacity = para_mach_capacity

        if big_m is None:
            # print(f"para_lmin={para_lmin}")
            # print(f"non-negative elements of para_lmin: {para_lmin[para_lmin>=0]}")
            self.big_m = get_big_m_value(
                para_p=para_p,
                para_h=para_h,
                para_lmin=para_lmin,
                para_a=para_a,
                infinity=inf_milp,
            )
            print(f"the inferred big_m value with Runzhong version is {self.big_m}")

        # # this part works because the leak of infinity to big_m
        # if big_m is None:
        #     self.big_m = get_m_value_old(
        #         para_p=para_p, para_h=para_h, para_lmin=para_lmin, para_a=para_a
        #     )
        else:
            self.big_m = big_m

        self.horizon = self.__class__.get_horizon(
            infinity=inf_milp,
            para_p=para_p,
            para_h=para_h,
            para_lmax=para_lmax,
            )
        # self.big_m = self.horizon

        # print(f"big_m: {self.big_m}")

        self.shift_durations = shift_durations
        self.operations_subset_indices = operations_subset_indices
        # self.num_workshifts = num_workshifts
        self.verbose = verbose
        self.var_c_max = None
        self.var_y = None
        self.var_c = None
        self.var_s = None
        self.var_x = None
        self.var_z = None
        self.model = None
        self.var_ws_assignments = None
        self.var_ws_starting_times = None

    def build_model_gurobi(self):
        """Build the mixed integer linear programming model with gurobi."""

        env = gp.Env(empty=True)
        env.setParam("OutputFlag", 0)
        env.setParam("LogToConsole", 0)
        env.start()

        model = gp.Model("fjss_mip")
        n_opt, n_mach = self.get_params()

        # create variables
        if self.matrix_variables:
            # if operation i is processed by machine m
            var_y = model.addMVar((n_opt, n_mach), vtype=GRB.BINARY, name="var_y")
            # if operation i is processed before operation j
            var_x = model.addMVar((n_opt, n_opt), vtype=GRB.BINARY, name="var_x")
            # if operation i is processed before and overlapped operation j in machine m
            var_z = model.addMVar(
                (n_opt, n_opt, n_mach), vtype=GRB.BINARY, name="var_z"
            )
            # starting time of operation i
            var_s = model.addMVar(n_opt, vtype=GRB.CONTINUOUS, name="var_s")
            # completion time of operation i
            var_c = model.addMVar(n_opt, vtype=GRB.CONTINUOUS, name="var_c")
        else:
            # if operation i is processed by machine m
            var_y = model.addMVars(n_opt, n_mach, vtype=GRB.BINARY, name="var_y")
            # if operation i is processed before operation j
            var_x = model.addMVars(n_opt, n_opt, vtype=GRB.BINARY, name="var_x")
            # if operation i is processed before and overlapped operation j in machine m
            var_z = model.addMVars(n_opt, n_opt, n_mach, vtype=GRB.BINARY, name="var_z")
            # starting time of operation i
            var_s = model.addMVars(n_opt, vtype=GRB.CONTINUOUS, name="var_s")
            # completion time of operation i
            var_c = model.addMVars(n_opt, vtype=GRB.CONTINUOUS, name="var_c")

        # objective
        # var_c_max = model.addVar(
        #     lb=1.0e-5, ub=self.horizon + 1, vtype=GRB.CONTINUOUS, name="var_c_max"
        # )
        var_c_max = model.addVar(lb=1.0e-5, name="var_c_max", vtype=GRB.CONTINUOUS)

        # var_c_max = model.addVar(
        #     name="var_c_max", lb=1e-5, ub=float("inf"), vtype=GRB.CONTINUOUS
        # )

        # add constraints
        for i in range(n_opt):
            # eq. (2)
            model.addConstr(var_c_max >= var_c[i], name="eq_2")
            # eq. (3)
            model.addConstr(
                var_c[i]
                >= var_s[i]
                + gp.quicksum(self.para_p[i, m] * var_y[i, m] for m in range(n_mach)),
                name="eq_3",
            )
            # eq. (4)
            model.addConstr(
                var_c[i]
                <= var_s[i]
                + gp.quicksum(
                    (self.para_p[i, m] + self.para_h[i, m]) * var_y[i, m]
                    for m in range(n_mach)
                ),
                name="eq_4",
            )
            # eq. (5)
            model.addConstr(
                gp.quicksum(var_y[i, m] for m in range(n_mach)) == 1, name="eq_5"
            )

        for i, j in it.product(range(n_opt), range(n_opt)):
            if i != j:
                # eq. (6)
                model.addConstr(
                    var_s[j] >= var_c[i] + self.para_lmin[i, j], name="eq_6"
                )
                # eq. (7)
                model.addConstr(
                    var_s[j] <= var_c[i] + self.para_lmax[i, j], name="eq_7"
                )

        for i, j, m in it.product(range(n_opt), range(n_opt), range(n_mach)):
            if i < j:
                expr_0 = self.big_m * (3 - var_x[i, j] - var_y[i, m] - var_y[j, m])
                # eq. (8)
                model.addConstr(
                    var_s[j] >= var_c[i] + self.para_a[i, j, m] - expr_0, name="eq_8"
                )
                # eq. (9)
                expr_1 = self.big_m * (2 + var_x[i, j] - var_y[i, m] - var_y[j, m])
                model.addConstr(
                    var_s[i] >= var_c[j] + self.para_a[j, i, m] - expr_1, name="eq_9"
                )
                # eq. (10)
                model.addConstr(
                    var_s[j] >= var_s[i] + self.para_delta[m] - expr_0, name="eq_10"
                )
                # eq. (11)
                model.addConstr(
                    var_s[i] >= var_s[j] + self.para_delta[m] - expr_1, name="eq_11"
                )
                # eq. (12)
                model.addConstr(
                    var_c[j] >= var_c[i] + self.para_delta[m] - expr_0, name="eq_12"
                )
                # eq. (13)
                model.addConstr(
                    var_c[i] >= var_c[j] + self.para_delta[m] - expr_1, name="eq_13"
                )
                # eq. (14)
                expr_2 = self.big_m * (
                    3 + var_z[i, j, m] - var_x[i, j] - var_y[i, m] - var_y[j, m]
                )
                model.addConstr(var_s[j] >= var_c[i] - expr_2, name="eq_14")
                # eq. (15)
                expr_3 = self.big_m * (
                    2 + var_z[j, i, m] + var_x[i, j] - var_y[i, m] - var_y[j, m]
                )
                model.addConstr(var_s[i] >= var_c[j] - expr_3, name="eq_15")

        # eq. (16)
        for i, m in it.product(range(n_opt), range(n_mach)):
            model.addConstr(
                gp.quicksum(
                    self.para_w[j, m] * var_z[i, j, m] for j in range(n_opt) if i != j
                )
                <= (self.para_mach_capacity[m] - self.para_w[i, m]) * var_y[i, m],
                name="eq_16",
            )

        # work shifts
        if self.shift_durations is not None:
            print("\nworking on work shifts related constraints\n")

            # not all the operations will need the work shift constraints
            if self.operations_subset_indices:
                operations_subset = {i: self.operations[i] for i in self.operations_subset_indices}
                # n_opt_subset = len(operations_subset)
            else:
                # n_opt_subset = n_opt
                operations_subset = self.operations

            eps = 1e-5
            value_m = self.horizon*10

            for i, _ in operations_subset.items():
                # TODO: check if this is necessary
                # the i-th operation should be processed in the i-th work shift, c_i - s_i <= shift_durations
                model.addConstr(
                var_c[i] - var_s[i] <= self.shift_durations, name="workshift_duration_limit_{i}"
                )

                # s_i <= (i+1)*shift_duration and c_i <= (i+1)*shift_duration
                var_auxiliary_a = model.addVar(
                    vtype=GRB.BINARY, name=f"var_auxiliary_a_{i}"
                )
                var_auxiliary_b = model.addVar(
                    vtype=GRB.BINARY, name=f"var_auxiliary_b_{i}"
                )

                # var_auxiliary_a indicates (i+1)*shift_duration >= s_i
                model.addConstr(
                    (i + 1) * self.shift_durations >= var_s[i] + eps - value_m * ( 1- var_auxiliary_a)
                )
                model.addConstr(
                    (i + 1) * self.shift_durations <= var_s[i] + value_m * var_auxiliary_a
                )
                # var_auxiliary_a indicates (i+1)*shift_duration >= c_i
                model.addConstr(
                    (i + 1) * self.shift_durations >= var_c[i] + eps - value_m * ( 1- var_auxiliary_a)
                )
                model.addConstr(
                    (i + 1) * self.shift_durations <= var_c[i] + value_m * var_auxiliary_a
                )
                # var_auxiliary_b indicates s_i > = (i+1)*shift_duration
                model.addConstr(
                    var_s[i] >= (i + 1) * self.shift_durations + eps - value_m * ( 1- var_auxiliary_b)
                )
                model.addConstr(
                    var_s[i] <= (i + 1) * self.shift_durations + value_m * var_auxiliary_b
                )
                # var_auxiliary_b indicates c_i > = (i+1)*shift_duration
                model.addConstr(
                    var_c[i] >= (i + 1) * self.shift_durations + eps - value_m * ( 1- var_auxiliary_b)
                )
                model.addConstr(
                    var_c[i] <= (i + 1) * self.shift_durations + value_m * var_auxiliary_b
                )
                # var_auxiliary_a indicates that var_auxiliary_1 and var_auxiliary_2 should be satisfied at the same time
                # model.addConstr(
                #     var_auxiliary_a == gp.and_(var_auxiliary_1, var_auxiliary_2)
                # )
                # model.addConstr(
                #     (var_auxiliary_a == 1) >> (var_auxiliary_1 + var_auxiliary_2 == 2)
                # )
                # model.addConstr(
                #     (var_auxiliary_1 + var_auxiliary_2 <= 1) >> (var_auxiliary_a == 0)
                # )

                # var_auxiliary_b indicates that var_auxiliary_1 and var_auxiliary_2 should be
                # satisfied at the same time
                # model.addConstr(
                #     var_auxiliary_b == gp.and_(var_auxiliary_3, var_auxiliary_4)
                # )
                # model.addConstr(
                #     (var_auxiliary_b == 1) >> (var_auxiliary_3 + var_auxiliary_4 == 2)
                # )
                # model.addConstr(
                #     (var_auxiliary_3 + var_auxiliary_4 <= 1) >> (var_auxiliary_b == 0)
                # )

                # var_auxiliary_a and var_auxiliary_b should not be satisfied at the same time, but
                # at least one of them should be satisfied
                model.addConstr(var_auxiliary_a + var_auxiliary_b == 1)

        # set the objective
        model.setObjective(var_c_max, GRB.MINIMIZE)

        self.var_c_max = var_c_max
        self.var_y = var_y
        self.var_c = var_c
        self.var_s = var_s
        self.var_x = var_x
        self.var_z = var_z
        self.model = model
        env.close()

    def solve_gurobi(self):
        """Solve the mixed integer linear programming model with gurobi."""
        # creates the solver and solve
        if self.model is None:
            self.build_model_gurobi()

        # add the threads
        if self.num_workers is None:
            # https://www.gurobi.com/documentation/current/refman/threads.html
            # The default value of 0 is an automatic setting.
            # It will generally use as many threads as there are virtual processors
            # We've made the pragmatic choice to impose a soft limit of 32 threads for the automatic setting (0)
            self.model.Params.Threads = 0
        # this is not recommended
        if self.num_workers is not None:
            self.model.Params.Threads = self.num_workers

        # set the number of solutions to be found
        # self.model.Params.PoolSolutions = 20

        self.model.optimize()

        if self.model.Status == GRB.OPTIMAL:
            print(f"the solution is : {self.model.objVal}")

            # assignments = dict()
            # start_times = dict()
            # end_times = dict()
            solved_operations = []

            var_y_solution = self.var_y.X
            var_s_solution = self.var_s.X
            var_c_solution = self.var_c.X

            # print(f"self.operations={self.operations}")
            # operation_names = list(self.operations.values())
            operation_ids = list(self.operations.values())

            for i, m in it.product(range(len(self.operations)), range(len(self.machines))):
                if var_y_solution[i, m] == 1:
                    # assignments[operation_ids[i]] = self.machines[m]
                    # start_times[operation_ids[i]] = var_s_solution[i]
                    # end_times[operation_ids[i]] = var_c_solution[i]
                    solved_operation = SolvedOperation(
                        id=operation_ids[i],
                        assigned_to=self.machines[m],
                        start_time=var_s_solution[i],
                        end_time=var_c_solution[i],
                    )
                    solved_operations.append(solved_operation)

            return FjsOutput(
                solved_operations=solved_operations,
                makespan=self.model.objVal,
            )
        else:
            print("No solution found.")
            return None

    def get_params(self):
        """Get parameters for the model."""
        n_opt = len(self.operations)
        n_mach = len(self.machines)

        return n_opt, n_mach

    @staticmethod
    def get_horizon(infinity, para_p, para_h, para_lmax):
        """Get the horizon."""
        # the horizon
        para_p_horizon = np.copy(para_p)
        para_p_horizon[para_p_horizon == infinity] = 0

        para_h_horizon = np.copy(para_h)
        para_h_horizon[para_h_horizon == infinity] = 0

        para_lmax_horizon = np.copy(para_lmax)
        para_lmax_horizon[para_lmax_horizon == infinity] = 0
        horizon = (
            np.max(para_p_horizon, axis=1)
            + np.max(para_h_horizon, axis=1)
            + np.max(para_lmax_horizon, axis=1)
        )

        # print("")
        # # print(f"para_p_horizon = {para_p_horizon}")
        # # print(f"para_h_horizon = {para_h_horizon}")
        # print(f"para_lmax_horizon = {para_lmax_horizon}")
        # print(f"para_lmax_horizon max is {np.max(para_lmax_horizon)}")

        horizon = np.sum(horizon)
        # print(f"\nhorizon={horizon}")

        return horizon
