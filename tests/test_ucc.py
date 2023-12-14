import numpy as np
from scipy.optimize import minimize
from qibochem.ansatz.hf_reference import hf_circuit
from qibochem.ansatz.ucc import ucc_circuit
from qibochem.driver.molecule import Molecule
from qibochem.measurement.expectation import expectation

def test_uccsd():
    # Define molecule and populate
    mol = Molecule([("Li", (0.0, 0.0, 0.0)), ("H", (0.0, 0.0, 1.2))])
    try:
        mol.run_pyscf()
    except ModuleNotFoundError:
        mol.run_psi4()


    # Apply embedding and boson encoding
    mol.hf_embedding(active=[1, 5])
    hamiltonian = mol.hamiltonian(oei=mol.embed_oei, tei=mol.embed_tei, constant=mol.inactive_energy)

    # Set parameters for the rest of the experiment
    n_qubits = mol.n_active_orbs
    n_electrons = mol.n_active_e

    # Build circuit
    circuit = hf_circuit(n_qubits, n_electrons)

    # UCCSD: Excitations
    d_excitations = [
        (_i, _j, _a, _b)
        for _i in range(n_electrons)
        for _j in range(_i + 1, n_electrons)  # Electrons
        for _a in range(n_electrons, n_qubits)
        for _b in range(_a + 1, n_qubits)  # Orbs
        if (_i + _j + _a + _b) % 2 == 0 and ((_i % 2 + _j % 2) == (_a % 2 + _b % 2))  # Spin
    ]
    s_excitations = [
        (_i, _a)
        for _i in range(n_electrons)
        for _a in range(n_electrons, n_qubits)
        if (_i + _a) % 2 == 0  # Spin-conservation
    ]
    # Sort excitations with very contrived lambda functions
    d_excitations = sorted(d_excitations, key=lambda x: (x[3] - x[2]) + (x[2] % 2))
    s_excitations = sorted(s_excitations, key=lambda x: (x[1] - x[0]) + (x[0] % 2))
    excitations = d_excitations + s_excitations
    n_excitations = len(excitations)
    # [(0, 1, 2, 3), (0, 2), (1, 3)] 3

    # UCCSD: Circuit
    all_coeffs = []
    for _ex in excitations:
        coeffs = []
        circuit += ucc_circuit(n_qubits, _ex, coeffs=coeffs)
        all_coeffs.append(coeffs)


    def electronic_energy(parameters):
        r"""
        Loss function for the UCCSD ansatz
        """
        all_parameters = []

        # UCC parameters
        # Expand the parameters to match the total UCC ansatz manually
        _ucc = parameters[:n_excitations]
        # Manually group the related excitations together
        ucc_parameters = [_ucc[0], _ucc[1], _ucc[2]]
        # Need to iterate through each excitation this time
        for _coeffs, _parameter in zip(all_coeffs, ucc_parameters):
            # Convert a single value to a array with dimension=n_param_gates
            ucc_parameter = np.repeat(_parameter, len(_coeffs))
            # Multiply by coeffs
            ucc_parameter *= _coeffs
            all_parameters.append(ucc_parameter)

        # Flatten all_parameters into a single list to set the circuit parameters
        all_parameters = [_x for _param in all_parameters for _x in _param]
        circuit.set_parameters(all_parameters)

        return expectation(circuit, hamiltonian)

    # Random initialization
    params = np.zeros(n_excitations)
    vqe = minimize(electronic_energy, params)

    lih_uccsd_energy = -7.847535097575567

    assert vqe.fun == pytest.approx(lih_uccsd_energy)


