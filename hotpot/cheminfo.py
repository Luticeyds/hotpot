"""
python v3.7.9
@Project: hotpot
@File   : cheminfo.py
@Author : Zhiyuan Zhang
@Date   : 2023/3/14
@Time   : 4:09
"""
import copy
import json
import os
import re
from abc import ABC, abstractmethod
from io import IOBase
from os import PathLike
from os.path import join as ptj
from pathlib import Path
from typing import *
from itertools import product

import numpy as np
from openbabel import openbabel as ob, pybel as pb
from rdkit import Chem

from hotpot import data_root
from hotpot.tanks import lmp
from hotpot.tanks.quantum import Gaussian
from hotpot.utils.load_chem_lib import library as _lib  # The chemical library


# Define Exceptions
class OperateOBMolFail(BaseException):
    """ Raise for any fail that trys to operate the OBMol """


class AddAtomFail(OperateOBMolFail):
    """ Raise when add an atom into Molecule fail """


class AddBondFail(OperateOBMolFail):
    """ Raise when add a bond into Molecule fail """


periodic_table = json.load(open(ptj(data_root, 'periodic_table.json'), encoding='utf-8'))
_symbols: List[str] = ['unknown'] + list(periodic_table.keys())
_max_valences = {n: v['max_valence'] for n, v in periodic_table.items()}
_max_total_bond_order = {n: v['max_total_bond_order'] for n, v in periodic_table.items()}

_stable_charges = {
    "H": 1, "He": 0,
    "Li": 1, "Be": 2, "B": 3, "C": 4, "N": -3, "O": -2, "F": -1, "Ne": 0,
    "Na": 1, "Mg": 2, "Al": 3, "Si": 4, "P": -3, "S": -2, "Cl": -1, "Ar": 0,
    "K": 1, "Ca": 2, "Sc": 3, "Ti": 4, "V": 5, "Cr": 4, "Mn": 3, "Fe": 2, "Co": 2, "Ni": 2, "Cu": 1, "Zn": 2, "Ga": 3, "Ge": 4, "As": -3, "Se": -2, "Br": -1, "Kr": 0,
    "Rb": 1, "Sr": 2, "Y": 3, "Zr": 4, "Nb": 5, "Mo": 6, "Tc": 7, "Ru": 4, "Rh": 3, "Pd": 2, "Ag": 1, "Cd": 2, "In": 3, "Sn": 2, "Sb": -3, "Te": -2, "I": -1, "Xe": 0,
    "Cs": 1, "Ba": 2, "La": 3, "Ce": 4, "Pr": 3, "Nd": 3, "Pm": 3, "Sm": 3, "Eu": 2, "Gd": 3, "Tb": 3, "Dy": 3, "Ho": 3, "Er": 3, "Tm": 3, "Yb": 3, "Lu": 3, "Hf": 4, "Ta": 5, "W": 6, "Re": 7, "Os": 4, "Ir": 3, "Pt": 2, "Au": 1, "Hg": 2, "Tl": 3, "Pb": 2, "Bi": 3, "Po": -2, "At": -1, "Rn": 0,
    "Fr": 1, "Ra": 2, "Ac": 3, "Th": 4, "Pa": 5, "U": 6, "Np": 6, "Pu": 6, "Am": 6, "Cm": 6, "Bk": 6, "Cf": 6, "Es": 6, "Fm": 6, "Md": 6, "No": 6, "Lr": 3, "Rf": 4, "Db": 5, "Sg": 6, "Bh": 7, "Hs": 8, "Mt": 8, "Ds": 8, "Rg": 8, "Cn": 8, "Nh": 8, "Fl": 8, "Mc": 8, "Lv": 8, "Ts": 8, "Og": 8
}


_bond_type = {
    'Unknown': 0,
    'Single': 1,
    'Double': 2,
    'Triple': 3,
    'Aromatic': 5,
}

_type_bond = {
    0: 'Unknown',
    1: 'Single',
    2: 'Double',
    3: 'Triple',
    5: 'Aromatic'
}

_ob_data_dict = {
    0: 'UndefinedData', 1: 'PairData', 2: 'EnergyData', 3: 'CommentData',
    4: 'ConformerData', 5: 'ExternalBondData', 6: 'RotamerList', 7: 'VirtualBondData',
    8: 'RingData', 9: 'TorsionData', 10: 'AngleData', 11: 'SerialNums',
    12: 'UnitCell', 13: 'SpinData', 14: 'ChargeData', 15: 'SymmetryData',
    16: 'ChiralData', 17: 'OccupationData', 18: 'DensityData', 19: 'ElectronicData',
    20: 'VibrationData', 21: 'RotationData', 22: 'NuclearData', 23: 'SetData',
    24: 'GridData', 25: 'VectorData', 26: 'MatrixData', 27: 'StereoData',
    28: 'DOSData', 29: 'ElectronicTransitionData', 16384: 'CustomData0', 16385: 'CustomData1',
    16386: 'CustomData2', 16387: 'CustomData3', 16388: 'CustomData4', 16389: 'CustomData5',
    16390: 'CustomData6', 16391: 'CustomData7', 16392: 'CustomData8', 16393: 'CustomData9',
    16394: 'CustomData10', 16395: 'CustomData11', 16396: 'CustomData12', 16397: 'CustomData13',
    19398: 'CustomData14', 16399: 'CustomData15'
}


class Wrapper(ABC):
    """
    A wrapper of chemical information and data.
    The _set_attrs method is used to set any keyword attribute, the attribute names, in the wrapper context, are defined
    by the keys from returned dict of _attr_setters; the values of the returned dict of _attr_setters are a collection
    of specific private method to wrapper and call openbabel method to set the attributes in openbabel object.
    """
    _data = {}  # all attributes of wrappers are stored into

    @property
    def _ob_obj(self) -> Union[ob.OBMol, ob.OBAtom, ob.OBBond, ob.OBAngle, ob.OBUnitCell]:
        return self._data.get('ob_obj')

    @property
    def _protected_data(self):
        """
        the protected attr in data which could not be replaced by call methods:
            - update_attr_data()
        """
        return ('ob_obj',)

    def _set_attrs(self, **kwargs):
        """    Set any atomic attributes by name    """
        attr_setters = self._attr_setters
        for name, value in kwargs.items():
            setter = attr_setters.get(name)

            if setter:  # if the attribute is exist in the object.
                assert isinstance(setter, Callable)
                setter(value)

            else:
                raise NameError(
                    f'the {self.__class__.__name__} is cannot be set by Atom.set(), '
                    f'the legal attrs include: {self._attr_setters.keys()}'
                )

    @property
    @abstractmethod
    def _attr_setters(self) -> Dict[str, Callable]:
        raise NotImplemented

    def _get_ob_comment_data(self, data_name: str):
        """ Retrieve OBCommentData according to specific data_name """
        comment = self._ob_obj.GetData(data_name)
        if comment:
            comment = ob.toCommentData(comment)
            return comment.GetData()
        return None

    @property
    def data(self) -> dict:
        """ Get the clone of attributes data dict """
        return copy.copy(self._data)

    def kwargs_setters(self):
        list_setters = [f'{k}: {s.__doc__}' for k, s in self._attr_setters.items()]
        print("\n".join(list_setters))

    def remove_ob_data(self, data_name: str):
        """ Remove specific OBData item by given data_name """
        self._ob_obj.DeleteData(data_name)

    def replace_attr_data(self, data: Dict):
        """ Replace the core data dict directly """
        self._data = data

    def set_ob_comment_data(self, attr_name: str, value: str):
        """ Set the OBCommentData for ob_obj """
        comment_data = ob.OBCommentData()

        comment_data.SetAttribute(attr_name)
        comment_data.SetData(value)

        self._ob_obj.CloneData(comment_data)

    @property
    def setter_keys(self):
        return list(self._attr_setters.keys())

    @property
    def temp_label(self):
        """ Retrieve the temp label """
        return self._get_ob_comment_data('temp_label')

    def update_attr_data(self, data: dict):
        """ update the attribute data by give dict """
        for data_attr in self._protected_data:
            if data.get(data_attr):
                data.pop(data_attr)

        self._data.update(data)


class Molecule(Wrapper, ABC):
    """"""
    # All Molecule attribute's items relating to molecule conformers
    conformer_items = (
        # the items are ranked by the number of values for each atom, for example:
        #   - the all_atom_charges and atom_spin_densities have 1 value for each atom, so they are placed in the second
        #     item (with the index 1)
        #   - the coordinates have 3 values for each atom, i.e., [x, y, z], so it is placed in the forth
        #     item (with the index 3）
        # For the molecular attributes, which have only one value for each conformer and represent the attribute
        # of whole molecule, they are place in the first item (with the index 0)
        ('all_energy',),
        ('all_atom_charges', 'all_atom_spin_densities'),
        (),
        ('all_coordinates', 'all_forces')
    )

    def __init__(self, ob_mol: ob.OBMol = None, _data: dict = None, **kwargs):
        if _data:
            self._data: dict = _data
        else:
            self._data: dict = {
                'ob_obj': ob_mol if ob_mol else ob.OBMol()
            }
        self._set_attrs(**kwargs)
        self._load_atoms()
        self._load_bonds()

    def __repr__(self):
        return f'Mol({self.ob_mol.GetSpacedFormula()})'

    def __add__(self, other: ['Molecule']):
        """
        Two Molecule objects could add to a new one to merge all of their conformers.
        All of information about the conformer will be merged to one.
        the other information will reserve the one in the left item
        Args:
            other: the right item

        Returns:
            Molecule
        """
        # When other obj is a Molecule or a child of Molecule
        if isinstance(other, Molecule):
            # If this one is compatible to the other
            if self.iadd_accessible(other):
                clone = self.copy()
                clone += other

                return clone

            # If the other one is compatible to this one
            if other.iadd_accessible(self):
                clone = other.copy()
                clone += self

                return clone

            # If they are compatible, but are Molecule or child of Molecule
            return bd.MolBundle([self, other])

        # if isinstance(other, MixSameAtomMol):
        #     return self.to_mix_mol() + other

        # When other obj is a MolBundle
        if isinstance(other, bd.MolBundle):
            return bd.MolBundle([self] + other.mols)

        else:
            raise TypeError('the Molecule only add with Molecule or MolBundle')

    def __iadd__(self, other):
        """
        Self add with other Molecule object with consist atoms list,
        The attributes or information about conformers will merge with the other,
        other attributes or information will be reserved
        Args:
            other: the merged Molecule object

        Returns:
            None
        """
        if not isinstance(other, Molecule):
            raise TypeError('the Molecule object is only allowed to add with other Molecule')

        # Check whether left and right Molecules have consist atom list
        if not self.iadd_accessible(other):
            raise AttributeError(
                'the self addition cannot be performed among molecules with different atoms list!'
            )

        return self._merge_conformer_attr(other)

    def __iter__(self):
        """ Return self with different configures """

        def configure_generator():
            for i in range(self.configure_number):
                self.configure_select(i)
                yield self

        return iter(configure_generator())

    def __next__(self):
        config_idx = self._data.get('config_idx', 0)
        try:
            self.configure_select(config_idx)
            self._data['config_idx'] = config_idx + 1
            return self
        except IndexError:
            raise StopIteration

    def __eq__(self, other):
        """ if two molecule with 1.0 similarity in 2FP fingerprint they are identical """
        if self.similarity(other) == 1.0:
            return True
        return False

    def _add_temp_atom_labels(self):
        """
        Add temp atom label, These label will assist in the implementation of certain functions,
        say Molecule.components. These label should be deleted after the assisted functions have
        been fulfilled, by call method _delete_temp_atom_labels(self)
        """
        for i, atom in enumerate(self.atoms):
            atom.set_ob_comment_data('temp_label', str(i))

    @staticmethod
    def _assign_coordinates(the_mol: 'Molecule', coordinates: np.ndarray):
        """ Assign coordinates for all atoms in the Molecule """
        if len(the_mol.atoms) != coordinates.shape[-2]:
            raise AttributeError('the coordinate matrix do not match the number of atoms')

        for new_mol_atom, new_atom_coord in zip(the_mol.atoms, coordinates):
            new_mol_atom.coordinates = new_atom_coord

    @property
    def _attr_setters(self) -> Dict[str, Callable]:
        return {
            'atoms.partial_charge': self._set_atoms_partial_charge,
            "identifier": self._set_identifier,
            "energy": self._set_energy,
            'all_energy': self._set_all_energy,
            'charge': self._set_mol_charge,
            'all_atom_charges': self._set_all_atom_charges,
            'all_atom_spin_densities': self._set_all_atom_spin_densities,
            'spin': self._set_spin_multiplicity,
            'atoms': self._set_atoms,
            'coordinates': self._set_coordinates,
            'mol_orbital_energies': self._set_mol_orbital_energies,
            'all_coordinates': self._set_all_coordinates,
            'all_forces': self._set_all_forces,
            'forces': self._set_forces,
            'crystal': self.create_crystal_by_matrix
        }

    def _create_ob_unit_cell(self):
        """ Create New OBUnitCell for the Molecule """
        ob_unit_cell = ob.OBUnitCell()
        self.ob_mol.CloneData(ob_unit_cell)

    def _delete_atom_temp_label(self):
        """ Remove temp label of all label """
        for a in self.atoms:
            a.remove_ob_data('temp_label')

    def _get_critical_params(self, name: str):
        critical_params = self._data.get('critical_params')
        if critical_params is None:
            critical_params = json.load(open(ptj(data_root, 'thermo', 'critical.json'))).get(self.smiles)
            if critical_params:
                self._data['critical_params'] = critical_params
                return critical_params[name]
            else:
                self._data['critical_params'] = False
                return False

        else:
            return critical_params[name]

    # TODO: Discard in last version
    @property
    def _ob_atom_indices(self):
        """ Get the indices for all OBAtom """
        indices = []

        try:
            num_ob_atoms = self.ob_mol.NumAtoms()
        # If there is none of atoms in the OBMol, raise the TypeError.
        except TypeError:
            num_ob_atoms = 0

        oba_id = 0  # the id for OBAtom in OBMol
        while len(indices) < num_ob_atoms:
            ob_atom = self.ob_mol.GetAtomById(oba_id)

            # if get a OBAtom
            if ob_atom:
                assert oba_id == ob_atom.GetId()
                indices.append(oba_id)

            oba_id += 1

        return indices

    def _pert_mol_generate(self, coordinates: Union[Sequence, np.ndarray]):
        """
        Generate new molecule obj according to new given coordinate
        Args:
            coordinates: New coordinates matrix

        Returns:
            Molecule, copy of this molecule with new coordinates
        """
        clone_mol = self.copy()
        self._assign_coordinates(clone_mol, coordinates)
        return clone_mol

    def _load_atoms(self) -> Dict[int, 'Atom']:
        """
        Construct atoms dict according to the OBAtom in the OBMol,
        where the keys of the dict are the ob_id of OBAtom and the values are the the constructed Atom objects
        the constructed dict would be place into the _data dict
        Returns:
            the atoms dict
        """
        atoms: Dict[int, Atom] = self._data.get('atoms', {})

        new_atoms = {}
        for new_ob_id, oba in enumerate(ob.OBMolAtomIter(self.ob_mol)):
            atom = atoms.get(oba.GetId(), Atom(oba, mol=self))
            oba.SetId(new_ob_id)
            new_atoms[new_ob_id] = atom

        self._data['atoms'] = new_atoms

        return new_atoms

    def _load_bonds(self) -> Dict[Tuple[int], 'Bond']:
        """
        Construct bonds dict according to the OBBond in the OBMol,
        where the keys of the dict are the ob_id of OBBond and the values are the the constructed Bond objects
        the constructed dict would be place into the _data dict
        Returns:
            dict of bonds
        """
        bonds: Dict = self._data.get('bonds', {})  # Get the stored bonds

        new_bonds = {}
        for new_ob_id, obb in enumerate(ob.OBMolBondIter(self.ob_mol)):
            bond = bonds.get(obb.GetId(), Bond(obb, self))  # Get old bond by old id
            obb.SetId(new_ob_id)  # Specify new id
            new_bonds[new_ob_id] = bond

        self._data['bonds'] = new_bonds

        return new_bonds

    @staticmethod
    def _melt_quench(
            elements: Dict[str, float], force_field: Union[str, os.PathLike], mol: "Molecule" = None,
            density: float = 1.0, a: float = 25., b: float = 25., c: float = 25.,
            alpha: float = 90., beta: float = 90., gamma: float = 90., time_step: float = 0.0001,
            origin_temp: float = 298.15, melt_temp: float = 4000., highest_temp: float = 10000.,
            ff_args: Sequence = (), path_writefile: Optional[str] = None, path_dump_to: Optional[str] = None,
            dump_every: int = 100,
    ):
        """ to perform the melt-quench by call lmp.AmorphousMaker """

        am = lmp.AmorphousMaker(elements, force_field, density, a, b, c, alpha, beta, gamma)
        mol = am.melt_quench(
            *ff_args, mol=mol, path_writefile=path_writefile, path_dump_to=path_dump_to, origin_temp=origin_temp,
            melt_temp=melt_temp, highest_temp=highest_temp, time_step=time_step, dump_every=dump_every
        )

        return mol

    def _merge_conformer_attr(self, other: 'Molecule'):
        """ Merge attributes, relate to molecule conformer, in other Molecule into this Molecule """

        def merge_attr(attr_name: str):
            """ Merge single conformer attr """
            left_attr = getattr(self, attr_name)
            right_attr = getattr(other, attr_name)

            if isinstance(left_attr, np.ndarray) and isinstance(right_attr, np.ndarray):
                self._data[attr_name] = np.concatenate([left_attr, right_attr])
            elif not (  # If the left and right values are not both empty, raise Attributes error.
                    (left_attr is None) or (isinstance(left_attr, np.ndarray) and (not left_attr.all())) and
                    (right_attr is None) or (isinstance(right_attr, np.ndarray) and (not right_attr.all()))
            ):
                raise AttributeError(
                    f'the configure relational attribute {attr_name} is different in:\n'
                    f'  - {self}_identifier: {self.identifier}\n'
                    f'  - {other}_identifier: {other.identifier}'
                    'they cannot to perform addition operation'
                )

        for i, items in enumerate(self.conformer_items):
            for item in items:
                merge_attr(item)

        return self

    @property
    def _protected_data(self):
        return 'ob_obj', 'atoms', 'bonds', 'angles'

    def _reorder_atom_ob_id(self):
        """ Reorder the ob id of atoms """
        new_atom_dict = {}
        for ob_id, atom in enumerate(self.atoms):
            atom.ob_atom.SetId(ob_id)
            new_atom_dict[ob_id] = atom

        self._data['atoms'] = new_atom_dict

    def _reorder_bond_ob_id(self):
        new_atom_dict = {}
        for ob_id, bond in enumerate(self.bonds):
            bond.ob_bond.SetId(ob_id)
            new_atom_dict[ob_id] = bond

        self._data['bonds'] = new_atom_dict

    def _reorganize_atom_indices(self):
        """ reorganize or rearrange the indices for all atoms """
        for i, ob_atom in enumerate(ob.OBMolAtomIter(self.ob_mol)):
            ob_atom.SetId(i)

    def _set_atoms(self, atoms_kwargs: List[Dict[str, Any]]):
        """ add a list of atoms by a list atoms attributes dict """
        for atom_kwarg in atoms_kwargs:
            a = Atom(**atom_kwarg)
            self.add_atom(a)

    def _set_atoms_partial_charge(self, partial_charges: [np.ndarray, Sequence[float]]):
        """ Set partial charges for all atoms in the molecule """
        if not isinstance(partial_charges, (np.ndarray, Sequence[int])):
            raise TypeError(
                f'the `partial_charges` should be np.ndarray or Sequence of float, not {type(partial_charges)}'
            )

        if self.atom_num != len(partial_charges):
            raise ValueError('the given partial charges should have same numbers with the number of atoms')

        for atom, partial_charge in zip(self.atoms, partial_charges):
            atom.partial_charge = partial_charge

    def _set_coordinates(self, coordinates: np.ndarray):
        """"""
        assert len(coordinates.shape) == 2
        assert coordinates.shape[0] == self.atom_num
        assert coordinates.shape[1] == 3

        for atom, coordinate in zip(self.atoms, coordinates):
            atom.coordinates = coordinate

    def _set_all_coordinates(self, all_coordinates: np.ndarray):
        """
        Assign the coordinates collection directly
        Args:
            all_coordinates: numpy array with the shape (M, N, 3), where the M is the number of coordinates
            in the collection, the N is the number of atoms of the molecule.

        Returns:
            None
        """
        if not isinstance(all_coordinates, np.ndarray):
            raise ValueError(
                f'the given all_coordinates must be a numpy.ndarray class, instead of {type(all_coordinates)}')

        if all_coordinates.shape[-1] != 3:
            raise ValueError(f'the coordinate must be 3 dimension, instead of {all_coordinates.shape[-1]}')

        if len(all_coordinates.shape) == 2:
            # if only give a group of coordinates
            all_coordinates = all_coordinates.reshape((-1, all_coordinates.shape[-2], 3))
        elif len(all_coordinates.shape) != 3:
            raise ValueError(
                f'the shape of given all_coordinates should with length 2 or 3, now is {len(all_coordinates.shape)}'
            )

        self._data['all_coordinates'] = all_coordinates

    def _set_atom_charges(self, charge: Union[Sequence, np.ndarray]):
        """ Set partial charge for each atoms in the mol """
        if not isinstance(charge, (Sequence, np.ndarray)):
            raise TypeError(f'the charge should be a sequence or np.ndarray, got {type(charge)}')

        if isinstance(charge, np.ndarray):
            charge = charge.flatten()

        if len(charge) != self.atom_num:
            raise ValueError('the number of charges do not match with the atom charge')

        for atom, ch in zip(self.atoms, charge):
            atom.partial_charge = ch

    def _set_all_atom_charges(self, charges: np.ndarray):
        """
        set groups of charges for each atoms in the mol, and each group of charges are corresponding to a
        conformer of the mol
        Args:
            charges: group of atoms with the shape of (C, N), where the C is the number of the conformer
             and the N is the number of the atom in the molecule
        """
        if not isinstance(charges, np.ndarray):
            raise TypeError('the arg charges should be np.ndarray')

        if len(charges.shape) != 2 and charges.shape[1] != self.atom_num:
            raise ValueError('the shape of the arg: charge should be (number_of_conformer, number_of_atoms),'
                             f'got the value with shape {charges.shape}')

        self._data['all_atom_charges'] = charges

    def _set_all_atom_spin_densities(self, group_spd: np.ndarray) -> None:
        """
        assign groups of spin densities for all atom in molecule, each group is corresponding to a conformer
        Args:
            group_spd(np.ndarray): group of spin densities, the numpy array with the (C, N) shape,
             where the C is the number of conformer, the N is the number of atoms
        """
        if not isinstance(group_spd, np.ndarray):
            raise TypeError('the arg group_spd should be np.ndarray')

        if len(group_spd.shape) != 2 and group_spd.shape[1] != self.atom_num:
            raise ValueError('the shape of the arg: group_spd should be (number_of_conformer, number_of_atoms),'
                             f'got the value with shape {group_spd.shape}')

        self._data['all_atom_spin_densities'] = group_spd

    def _set_atom_spin_densities(self, spd: Union[Sequence, np.ndarray]):
        """ assign the spin density for each of atoms in the mol """
        if not isinstance(spd, (Sequence, np.ndarray)):
            raise TypeError(f'the charge should be a sequence or np.ndarray, got {type(spd)}')

        if isinstance(spd, np.ndarray):
            spd = spd.flatten()

        if len(spd) != self.atom_num:
            raise ValueError('the number of charges do not match with the atom charge')

        for atom, sp in zip(self.atoms, spd):
            atom.spin_density = sp

    def _set_forces(self, forces: np.ndarray):
        """ Set the force vectors for each atoms in the molecule """
        if not isinstance(forces, np.ndarray):
            raise TypeError('the forces should be np.ndarray')

        if len(forces.shape) != 2:
            raise ValueError('the length of shape of forces should be 2')

        if forces.shape[-2] != self.atom_num:
            raise ValueError('the give forces do not match to the number of atoms')

        for atom, force_vector in zip(self.atoms, forces):
            atom.force_vector = force_vector

    def _set_all_forces(self, all_forces: np.ndarray):
        """ Store the force matrix into the attribute dict """
        if not isinstance(all_forces, np.ndarray):
            raise TypeError('the all_forces should be np.ndarray')

        if len(all_forces.shape) != 3:
            raise ValueError('the length of shape of all_forces should be 3')

        if all_forces.shape[-2] != self.atom_num:
            raise ValueError('the give all_forces do not match to the number of atoms')

        self._data['all_forces'] = all_forces

    def _set_mol_charge(self, charge: int):
        self.ob_mol.SetTotalCharge(charge)

    def _set_mol_orbital_energies(self, orbital_energies: list[np.ndarray]):
        self._data['mol_orbital_energies'] = orbital_energies[0]

    def _set_energy(self, energy: float):
        """ set the energy """
        self.ob_mol.SetEnergy(energy)

    def _set_all_energy(self, all_energy: Union[float, np.ndarray], config_index: Optional[int] = None):
        """ set the energy for all configures """
        if isinstance(all_energy, float):
            self._data['all_energy'] = np.array([all_energy])
        else:
            all_energy = all_energy.flatten()
            self._data['all_energy'] = all_energy

    def _set_identifier(self, identifier):
        self.ob_mol.SetTitle(identifier)

    def _set_spin_multiplicity(self, spin):
        self.ob_mol.SetTotalSpinMultiplicity(spin)

    @property
    def acentric_factor(self):
        return self._get_critical_params('acentric_factor')

    def add_atom(self, atom: Union["Atom", str, int], **atom_attrs):
        """
        Add a new atom out of the molecule into the molecule.
        Args:
            atom(Atom|str|int):

        atom_kwargs(kwargs for this added atom):
            atomic_number(int): set atomic number
            symbol(str): set atomic symbol
            coordinates(Sequence, numpy.ndarray): coordinates of the atom
            partial_charge:
            label:
            spin_density:

        Returns:
            the copy of atom in the molecule
        """
        oba = ob.OBAtom()  # Initialize a new OBAtom
        data = None
        if isinstance(atom, str):
            oba.SetAtomicNum(_symbols.index(atom))
        elif isinstance(atom, int):
            oba.SetAtomicNum(atom)
        elif isinstance(atom, Atom):
            oba.SetAtomicNum(atom.atomic_number)
            data = atom.data  # Copy the give atoms data

        # add OBAtom to the OBMol
        success = self.ob_mol.AddAtom(oba)

        if success:
            atom = self.atoms[-1]  # Retrieve the added atom

            if data:
                atom.update_attr_data(data)  # replicant the old atom's data to the new

            atom.set(**atom_attrs)  # Set attributes by kwargs

            return atom

        else:
            raise AddAtomFail(f'Add the atom {atom} into Molecule fail')

    def add_bond(
            self,
            atom1: Union[str, int, 'Atom'],
            atom2: Union[str, int, 'Atom'],
            bond_type: Union[str, int],
    ):
        """ Add a new bond into the molecule """
        inputs = (atom1, atom2)
        atoms: List[Atom] = []
        for a in inputs:
            if isinstance(a, int):
                atoms.append(self.atoms_dict[a])
            if isinstance(a, Atom):
                atoms.append(a)
            if isinstance(a, str):
                atoms.append(self.atom(a))

        # Represent the bond type by int, refer to _bond_type dict
        bond_type = bond_type if isinstance(bond_type, int) else _bond_type[bond_type]

        # Try to add new OBMol
        # 'openbabel' has an odd behave that `index` of the `OBAtom` with various origin in the `OBMol`.
        # the `Id` of `OBAtom` from 0; but the `Idx` of `OBAtom` from 1.
        # To meet the convention, the `Id` is selected to be the unique `index` to specify `Atom`.
        # However, when try to add a `OBBond` to link each two `OBAtoms`, the `Idx` is the only method
        # to specify the atoms, so our `index` in `Atom` are added 1 to match the 'Idx'
        success = self.ob_mol.AddBond(atoms[0].ob_idx, atoms[1].ob_idx, bond_type)

        if success:
            new_bond_ob_id = [obb for obb in (ob.OBMolBondIter(self.ob_mol))][-1].GetId()
            bond = self._load_bonds()[new_bond_ob_id]  # the new atoms should place in the terminal of the bond list

        elif atoms[0].ob_id not in self.atom_indices:
            raise KeyError("the start atom1 doesn't exist in molecule")

        elif atoms[1].ob_id not in self.atom_indices:
            raise KeyError("the end atom2 doesn't exist in molecule")

        else:
            raise RuntimeError('add bond not successful!')

        # Return the bond have added into the molecule
        return bond

    def add_hydrogens(self, polar_only: bool = False, correct_for_ph: bool = False, ph: float = 1.0):
        """
        add hydrogens for the molecule
        Args:
            ph: add hydrogen in which PH environment
            polar_only: Whether to add hydrogens only to polar atoms (i.e., not to C atoms)
            correct_for_ph: Correct for pH by applying the OpenBabel::OBPhModel transformations
        """
        self.ob_mol.AddHydrogens(polar_only, correct_for_ph, ph)
        self._load_atoms()
        self._load_bonds()
        # TODO: Beta, test feature
        for atom in self.atoms:
            atom.remove_redundant_hydrogen()

    def add_pseudo_atom(self, symbol: str, mass: float, coordinates: Union[Sequence, np.ndarray], **kwargs):
        """ Add pseudo atom into the molecule """
        list_pseudo_atom = self._data.setdefault('pseudo_atoms', [])
        pa = PseudoAtom(symbol, mass, coordinates, mol=self, molecule=self, **kwargs)
        list_pseudo_atom.append(pa)

    @property
    def all_coordinates(self) -> np.ndarray:
        """
        Get the collections of the matrix of all atoms coordinates,
        each matrix represents a configure.
        The return array with shape of (C, N, 3),
        where the C is the number of conformers, the N is the number of atoms
        """
        all_coordinates = self._data.get('all_coordinates')
        if isinstance(all_coordinates, np.ndarray):
            return all_coordinates
        else:
            return self.coordinates.reshape((-1, self.atom_num, 3))

    @property
    def all_energy(self):
        return self._data.get('all_energy')

    @property
    def angles(self):
        return [Angle(self, a_idx) for a_idx in ob.OBMolAngleIter(self.ob_mol)]

    def assign_bond_types(self):
        self.ob_mol.PerceiveBondOrders()

    def atom(self, id_label: Union[int, str]) -> 'Atom':
        """ get atom by label or idx """
        if isinstance(id_label, str):

            if not self.is_labels_unique:
                raise AttributeError(
                    'the label is not unique, cannot get atom by label. try to get atom by ob_id '
                    'or normalize the label before'
                )

            for atom in self.atoms:
                if atom.label == id_label:
                    return atom
            raise KeyError(f'No atom with label {id_label}')

        elif isinstance(id_label, int):
            return self.atoms_dict[id_label]
        else:
            raise TypeError(f'the given idx_label is expected to be int or string, but given {type(id_label)}')

    @property
    def atom_num(self):
        return self.ob_mol.NumAtoms()

    @property
    def atoms(self) -> List['Atom']:
        """
        Generate dict of Atom objects into the data repository.
        Return list of Atom objects with the order their index.
        """
        atoms = self._load_atoms()
        return list(atoms.values())

    @property
    def atoms_dict(self) -> Dict[int, 'Atom']:
        return self._load_atoms()

    @property
    def all_atoms(self):
        return self.atoms + self.pseudo_atoms

    @property
    def atom_charges(self) -> np.ndarray:
        """ Return all atoms charges as a numpy array """
        return np.array([a.partial_charge for a in self.atoms])

    @property
    def all_atom_charges(self) -> np.ndarray:
        """ Return all atoms charges as a numpy array for every conformers """
        all_atom_charges = self._data.get('all_atom_charges')
        if isinstance(all_atom_charges, np.ndarray):
            return all_atom_charges
        return self.atom_charges.reshape((-1, self.atom_num))

    @property
    def atom_indices(self) -> list[int]:
        return [a.ob_id for a in self.atoms]

    @property
    def atom_labels(self) -> list[str]:
        return [a.label for a in self.atoms]

    @property
    def atom_spin_densities(self) -> np.ndarray:
        return np.array([a.spin_density for a in self.atoms])

    @property
    def all_atom_spin_densities(self):
        all_atom_spin_densities = self._data.get('all_atom_spin_densities')
        if all_atom_spin_densities is not None:
            return all_atom_spin_densities
        return self.atom_spin_densities.reshape((-1, self.atom_num))

    @property
    def atomic_numbers(self):
        return tuple(a.atomic_number for a in self.atoms)

    @property
    def atomic_symbols(self):
        return tuple(a.symbol for a in self.atoms)

    def bond(self, atom1: Union[int, str], atom2: Union[int, str], miss_raise: bool = False) -> 'Bond':
        """
        Return the Bond by given atom index labels in the bond ends
        if the bond is missing in the molecule, return None if given miss_raise is False else raise a KeyError
        Args:
            atom1(int|str): index or label of atom in one of the bond end
            atom2(int|str): index or label of atom in the other end of the bond
            miss_raise(bool): Whether to raise error when can't find the bond

        Returns:
            Bond

        Raises:
            KeyError: when can't find the bond, and the miss_raise passing True

        """
        atom1: Atom = self.atom(atom1)
        atom2: Atom = self.atom(atom2)
        ob_bond = self.ob_mol.GetBond(atom1.ob_atom, atom2.ob_atom)

        if ob_bond:
            return Bond(ob_bond, self)

    @property
    def bond_pair_keys(self):
        return [b.pair_key for b in self.bonds]

    @property
    def bonds(self):
        bonds = self._load_bonds()
        return list(bonds.values())

    @property
    def bonds_dict(self) -> Dict[Tuple[int], 'Bond']:
        return self._load_bonds()

    def build_bonds(self):
        self.ob_mol.ConnectTheDots()

    def build_conformer(self, force_field: str = 'UFF', steps: int = 50):
        """ build 3D coordinates for the molecule """
        pymol = pb.Molecule(self.ob_mol)
        pymol.make3D(force_field, steps)

    @property
    def center_of_masses(self):
        return (self.masses * self.coordinates.T).T.sum(axis=0) / self.masses.sum()

    @property
    def center_of_shape(self):
        return self.coordinates.mean(axis=0)

    @property
    def charge(self):
        return self.ob_mol.GetTotalCharge()

    @charge.setter
    def charge(self, charge):
        self._set_mol_charge(charge)

    def clean_bonds(self):
        """ Remove all bonds """
        # Iterate directly will fail.
        ob_bonds = [ob_bond for ob_bond in ob.OBMolBondIter(self.ob_mol)]
        for ob_bond in ob_bonds:
            self.ob_mol.DeleteBond(ob_bond)

    def clean_configures(self, pop: bool = False):
        """ clean all config save inside the molecule """
        try:
            all_coordinates = self._data.pop('all_coordinates')
        except KeyError:
            all_coordinates = None

        if pop:
            return all_coordinates

    @property
    def components(self):
        """ get all fragments don't link each by any bonds """
        # Add temp label for each atom first
        self._add_temp_atom_labels()
        parent_atom_dict = {a.temp_label: a.data for a in self.atoms}

        components = [self.__class__(obc) for obc in self.ob_mol.Separate()]

        # Transfer the parent data attr to the children
        for c in components:
            for a in c.atoms:
                a.update_attr_data(parent_atom_dict[a.temp_label])
                a.remove_ob_data('temp_label')

        # remove temp labels of all atoms
        self._delete_atom_temp_label()

        return components

    @property
    def configure_number(self):
        all_coordinates = self._data.get('all_coordinates')
        if isinstance(all_coordinates, np.ndarray):
            return all_coordinates.shape[0]
        else:
            return 1

    def configure_select(self, config_idx: int):
        """ select specific configure by index """

        def assign_numpy_attrs(attrs_name: str, setter: Callable):
            attrs = self._data.get(attrs_name)
            if isinstance(attrs, np.ndarray):
                try:
                    attr = attrs[config_idx]
                except IndexError:
                    attr = None
            else:
                attr = None

            if isinstance(attr, np.ndarray) or attr:
                setter(attr)

        all_coordinates = self._data.get('all_coordinates')
        if all_coordinates is None and config_idx:
            raise IndexError('Only one configure here!')

        # assign the coordinates for the molecule
        coordinates = all_coordinates[config_idx]
        self._assign_coordinates(self, coordinates)

        assign_numpy_attrs('all_energy', self._set_energy)

        assign_numpy_attrs('all_atom_charges', self._set_atom_charges)

        assign_numpy_attrs('all_atom_spin_densities', self._set_atom_spin_densities)

        assign_numpy_attrs('all_forces', self._set_forces)

    @property
    def coordinates(self) -> np.ndarray:
        """
        Get the matrix of all atoms coordinates,
        where the row index point to the atom index;
        the column index point to the (x, y, z)
        """
        return np.array([atom.coordinates for atom in self.atoms], dtype=np.float64)

    def copy(self) -> 'Molecule':
        """ Get a clone of this Molecule """
        clone = Molecule(self.ob_copy())
        clone._load_atoms()
        clone._load_bonds()

        # Copy the Molecule's attr data to the clone one
        clone.update_attr_data(self.data)
        # Copy the Atoms' attr data to the clone ones
        for atom in clone.atoms:
            atom.update_attr_data(self.atoms_dict[atom.ob_id].data)
            atom.molecule = clone
        # Copy the Bonds' attr data to the lone ones
        for bond in clone.bonds:
            bond.update_attr_data(self.bonds_dict[bond.ob_id].data)
            bond.molecule = clone

        return clone

    def compact_crystal(self, inplace=False):
        """"""
        mol = self if inplace else self.copy()
        lattice_params = np.concatenate((self.xyz_diff, [90., 90., 90.]))

        mol.make_crystal(*lattice_params)

        return mol

    def create_atom(self, symbol: str, **kwargs):
        """
        Discarded !!!
        Create a new atom into the molecule
        Args:
            symbol: the atomic symbol
            **kwargs: any attribute for the atom

        Returns:
            the created atom in the molecule
        """
        OBAtom: ob.OBAtom = self.ob_mol.NewAtom()
        atomic_number = periodic_table[symbol]['number']
        OBAtom.SetAtomicNum(atomic_number)
        atom = Atom(OBAtom, mol=self, **kwargs)

        return atom

    def create_crystal_by_vectors(
            self,
            va: Union[Sequence, np.ndarray],
            vb: Union[Sequence, np.ndarray],
            vc: Union[Sequence, np.ndarray]
    ):
        """ Create a new crystal with specified cell vectors for the Molecule """
        self._create_ob_unit_cell()
        self.crystal().set_vectors(va, vb, vc)

    def create_crystal_by_matrix(self, matrix: np.ndarray):
        """ Create a new crystal with specified cell matrix for the molecule """
        if not (np.logical_not(matrix >= 0.).any() and np.logical_not(matrix < 0.).any()) and np.linalg.det(matrix):
            self._create_ob_unit_cell()
            self.crystal().set_matrix(matrix)
            # self.crystal().space_group = 'P1'

    @classmethod
    def create_aCryst_by_mq(
            cls, elements: Dict[str, float], force_field: Union[str, os.PathLike],
            density: float = 1.0, a: float = 25., b: float = 25., c: float = 25.,
            alpha: float = 90., beta: float = 90., gamma: float = 90., time_step: float = 0.0001,
            origin_temp: float = 298.15, melt_temp: float = 4000., highest_temp: float = 10000.,
            ff_args: Sequence = (), path_writefile: Optional[str] = None, path_dump_to: Optional[str] = None,
            dump_every: int = 100
    ):
        """
        Create a Amorphous crystal materials by Melt-Quench process.
        This process is performed by LAMMPS package, make sure the LAMMPS is accessible.
        A suitable force field is required for the process are performed correctly.
        Args:
            elements(dict[str, float]): Dict of elements and their composition ratio
            force_field(str, os.PathLike): The name of force filed or the path to load a force filed. The name
             of the force filed is refer to the relative path to the 'hotpot_root/data/force_field'.
            density: the demand density for the created amorphous crystal
            a: the length of a vector in the crystal
            b: the length of b vector in the crystal
            c: the length of c vector in the crystal
            alpha: alpha angle of crystal param.
            beta: beta angle of crystal param.
            gamma: gamma angle of crystal param
            time_step: time interval between path integrals when performing melt-quench
            origin_temp: the initial temperature before melt
            melt_temp: the round melting point to the materials
            highest_temp: the highest temperature to liquefy the materials
            ff_args: the arguments the force file requried, refering the LAMMPS pair_coeff:
             "pair_coeff I J args" url: https://docs.lammps.org/pair_coeff.html
            path_writefile: the path to write the final material (screenshot) to file, if not specify, not save.
            path_dump_to:  the path to save the trajectory of the melt-quench process, if not specify not save.
            dump_every: the step interval between each dump operations

        Returns:
            Molecule, a created amorphous material
        """
        return cls._melt_quench(
            elements=elements, force_field=force_field, density=density,
            a=a, b=b, c=c, alpha=alpha, beta=beta, gamma=gamma, time_step=time_step,
            origin_temp=origin_temp, melt_temp=melt_temp, highest_temp=highest_temp,
            ff_args=ff_args, path_writefile=path_writefile, path_dump_to=path_dump_to,
            dump_every=dump_every
        )

    @property
    def critical_pressure(self):
        return self._get_critical_params('pressure')

    @property
    def critical_temperature(self):
        return self._get_critical_params('temperature')

    def crystal(self):
        """ Get the Crystal containing the Molecule """
        cell_index = ob.UnitCell  # Get the index the UnitCell data save
        cell_data = self.ob_mol.GetData(cell_index)

        if cell_data:
            ob_unit_cell = ob.toUnitCell(cell_data)
            return Crystal(ob_unit_cell, molecule=self)
        else:
            return None

    def determine_mol_charge(self):
        """ Determining the molecular charge """
        if not self.metals:  # if the molecule don't have any metal:
            self.charge = self.read_from(self.dump('mol2'), 'mol2').charge
        else:
            clone = self.copy()
            clone.remove_metals()

            organic_charge = clone.read_from(clone.dump('mol2'), 'mol2').charge
            metal_charge = sum(_stable_charges[m.symbol] for m in self.metals)

            self.charge = organic_charge + metal_charge

    def dump(self, fmt: str, *args, **kwargs) -> Union[str, bytes, dict]:
        """"""
        dumper = Dumper(fmt=fmt, source=self, *args, **kwargs)
        return dumper()

    @property
    def elements(self) -> list[str]:
        return re.findall(r'[A-Z][a-z]*', self.formula)

    @property
    def energy(self):
        """ Return energy with kcal/mol as default """
        return self.ob_mol.GetEnergy()

    def feature_matrix(self, *feature_names: Sequence) -> np.ndarray:
        """ Retrieve the feature matrix (collections of feature vector for every atoms),
         The default feature is `atomic_orbital`, if the feature names not be specified, the `atomic_orbital` will be
         retrieved.
         Args:
             feature_names: the feature names are offered in hotpot/data/periodic_table.json
         """
        if not feature_names:
            feature_names = ('atomic_orbital',)

        # Matrix with shape (atom_numbers, feature_length)
        return np.stack([atom.element_features(*feature_names) for atom in self.atoms])

    def fingerprint(self, fptype: Literal['FP2', 'FP3', 'FP4', 'MACCS'] = 'FP2'):
        """
        Calculate the molecular fingerprint for this molecule, the supporting fingerprint include:

        1. "FP2": The FP2 fingerprint is a path-based fingerprint that encodes the presence of linear
        fragments up to 7 atoms long. It is a 1024-bit fingerprint and is commonly used for substructure
        searches and similarity calculations.

        2. "FP3": The FP3 fingerprint is designed for searching 3D conformations, such as those found
        in protein-ligand complexes. It encodes the presence of particular pharmacophoric features,
        such as hydrogen bond donors, acceptors, and hydrophobic regions.

        3. "FP4": The FP4 fingerprint is a circular fingerprint based on the Morgan algorithm. It
        captures information about the local environment of each atom in the molecule, up to a certain
        radius. It is useful for similarity calculations and machine learning tasks.

        4. "MACCS": The MACCS fingerprint is a 166-bit structural key-based fingerprint. It represents
        the presence of specific substructures or functional groups defined by the MACCS keys. It is
        commonly used for similarity calculations and substructure searches.

        Return:
            the Fingerprint object in pybel module
        """
        return pb.Molecule(self.ob_mol).calcfp(fptype)

    @property
    def forces(self):
        """ return the all force vectors for all atoms in the molecule """
        return np.vstack((atom.force_vector for atom in self.atoms))

    @property
    def all_forces(self):
        """ the force matrix for all configure """
        force_matrix = self._data.get("all_forces")
        if isinstance(force_matrix, np.ndarray):
            return force_matrix
        return self.forces

    @property
    def formula(self) -> str:
        return self.ob_mol.GetSpacedFormula()

    def gaussian(
            self,
            g16root: Union[str, PathLike],
            link0: Union[str, List[str]],
            route: Union[str, List[str]],
            path_log_file: Union[str, PathLike] = None,
            path_err_file: Union[str, PathLike] = None,
            inplace_attrs: bool = False,
            *args, **kwargs
    ) -> (Union[None, str], str):
        """
        calculation by gaussion.
        for running the method normally, MAKE SURE THE Gaussian16 HAVE BEEN INSTALLED AND ALL ENV VAR SET RITHT !!
        Args:
            g16root: the dir Gaussian16 software installed
            link0: the link0 command in gjf script
            route: the route command in gjf script
            path_log_file: Optional, the path to save the out.log file. If not given, the logfile won't be write
             to disk
            path_err_file: optional, the path to save the error log file. If not given, the err file won't be write
             to disk
            inplace_attrs: Whether to inplace self attribute according to the results from attributes
            *args:
            **kwargs:

        Returns:
            the standard output of g16 log file(string), the standard output of g16 err file(string)
        """
        # For 2d molecule, build its confomer by universal force field first
        if not self.has_3d:
            self.build_conformer()

        # Make the input gjf script
        script = self.dump('gjf', *args, link0=link0, route=route, **kwargs)

        # Run Gaussian16
        with Gaussian(g16root) as gaussian:
            stdout, stderr = gaussian.run(script, args, **kwargs)

            # save the calculate result into the molecule data dict
            self._data['gaussian_output'] = stdout
            self._data['gaussian_parse_data'] = gaussian.data

            # Inplace the self attribute according to the result from gaussian
            if inplace_attrs:
                self._set_attrs(**gaussian.molecule_setter_dict)

        # Save log file
        if path_log_file:
            with open(path_log_file, 'w') as writer:
                writer.write(stdout)

        # Save error file
        if path_err_file:
            with open(path_err_file, 'w') as writer:
                writer.write(stderr)

        # return results and error info
        return stdout, stderr

    def gcmc(
            self, *guest: 'Molecule', force_field: Union[str, os.PathLike] = None,
            work_dir: Union[str, os.PathLike] = None, T: float = 298.15, P: float = 1.0, **kwargs
    ):
        """
        Run gcmc to determine the adsorption of guest,
        Args:
            self: the framework as the sorbent of guest molecule
            guest(Molecule): the guest molecule to be adsorbed into the framework
            force_field(str|PathLike): the path to force field file or the self-existent force file contained
             in force field directory (in the case, a str should be given as a relative path from the root of
             force field root to the specified self-existent force filed). By default, the force field is UFF
             which in the relative path 'UFF/LJ.json' for the force field path.
            work_dir: the user-specified dir to store the result of GCMC and log file.
            T: the environmental temperature (default, 298.15 K)
            P: the relative pressure related to the saturation vapor in the environmental temperature.
        """
        from tanks.lmp.gcmc import LjGCMC
        gcmc = LjGCMC(self, force_field, *guest, work_dir=work_dir, T=T, P=P, **kwargs)
        return gcmc.run()

    def generate_metal_ligand_pair(
            self, metal_symbol: str,
            acceptor_atoms: Sequence = ('O',),
            opti_force_field: str = 'UFF',
            assign_metal_charge: bool = False
    ) -> Generator['Molecule', None, None]:
        """
        This method could work if the molecule is an organic ligand, or raise AttributeError.
        Generate metal-ligand pair by link metal with acceptor atoms in the organic ligand.

        Args:
            metal_symbol: which metal element link to the ligand
            acceptor_atoms: which elements to be acceptor atom to link to metal
            opti_force_field: which force field could be used to optimize the configuration of ligand and M-L pair.
            assign_metal_charge: whether to assign the stable charge to metal cation

        Return:
            A generator for M-L pair
        """
        ligand = self.copy()
        for atom in ligand.atoms:
            if atom.symbol in acceptor_atoms:
                # copy the ligand as the embryo of metal-ligand pairs
                pair = ligand.copy()

                # Replace the correspondent atom in the pair embryo, i.e., the accepting atom
                acc_atom = pair.atom(atom.ob_id)

                # assign the initial coordinates, if the pair has 3d conformer
                # the sum of vector of relative position relate to the accepting atom
                if pair.has_3d:
                    sum_relative_coordinates = sum([c for _, c in acc_atom.neighbours_position])
                    metal_init_coordinates = acc_atom.coordinates_array - sum_relative_coordinates

                    # add metal atom into the acceptor_ligand
                    added_metal = pair.add_atom(
                        metal_symbol,
                        coordinates=metal_init_coordinates,
                        formal_charge=_stable_charges[metal_symbol] if assign_metal_charge else 0
                    )

                else:  # If the pair has not 3d conformer, add the metal directly
                    added_metal = pair.add_atom(
                        metal_symbol,
                        formal_charge=_stable_charges[metal_symbol] if assign_metal_charge else 0
                    )

                # add the coordinating bond between metal atom and acceptor atoms
                pair.add_bond(added_metal, acc_atom, 1)

                # Add hydrogens
                pair.add_hydrogens()

                # localize optimization of M-L pair by classical force field, if the pair has 3d
                if pair.has_3d:
                    pair.localed_optimize(opti_force_field)

                pair.identifier = pair.smiles
                yield pair

    def generate_pairs_bundle(
            self, metal_symbol: str,
            acceptor_atoms: Sequence = ('O',),
            opti_force_field: str = 'UFF',
            assign_metal_charge: bool = False
    ) -> 'PairBundle':
        """
        Generate metal-ligand pairs by bind this ligand with proposed, and put this ligand, metal and all pairs,
        which are assembled by the ligand and metal, into a PairBundle objects.
        Args:
            metal_symbol(str): the symbol of proposed metal
            acceptor_atoms(Sequence): the atoms to form bond with the proposed metal, the default is Oxygen
            opti_force_field(str): the force field to optimize the conformer of this ligand and the generated
             pairs.
            assign_metal_charge: whether to assign stable charge for metal cation

        Returns:
            PairBundle with this ligand, proposed metal and the pairs
        """
        return PairBundle(
            metal=Atom(symbol=metal_symbol),
            ligand=self,
            pairs=list(self.generate_metal_ligand_pair(
                metal_symbol,
                acceptor_atoms,
                opti_force_field,
                assign_metal_charge
            )),
        )

    def graph_representation(self, *feature_names):
        return self.identifier, self.feature_matrix(*feature_names), self.link_matrix

    @property
    def has_3d(self):
        """ Whether atoms in the molecule have 3d coordinates """
        return self.ob_mol.Has3D()

    @property
    def hydrogens(self):
        return [a for a in self.atoms if a.is_hydrogen]

    @property
    def hydrogens_due_number(self):
        """ the number of hydrogens when all hydrogens are completed """
        clone = self.__class__.read_from(self.smiles, 'smi')
        clone.add_hydrogens()
        return clone.hydrogens_number

    @property
    def hydrogens_number(self):
        return len(self.hydrogens)

    @property
    def identifier(self):
        return self.ob_mol.GetTitle()

    @identifier.setter
    def identifier(self, value):
        self.ob_mol.SetTitle(value)

    def iadd_accessible(self, other):
        if self.atomic_numbers == other.atomic_numbers:
            return True
        return False

    @property
    def inchi(self):
        return self.dump('inchi').strip()

    @property
    def is_labels_unique(self):
        """ Determine whether all atom labels are unique """
        return len(set(self.labels)) == self.atom_num

    @property
    def is_organic(self):
        """ To judge whether the molecule is organic, an organic compound is with carbon atoms and without metal """
        if any(a.is_metal for a in self.atoms):
            return False
        elif any(a.symbol == 'C' for a in self.atoms):
            return True

        return False

    def ob_copy(self):
        """ Return a clone of OBMol of the Molecule """
        return ob.OBMol(self.ob_mol)

    @property
    def ob_mol(self):
        return self._data['ob_obj']

    def ob_mol_pop(self):
        data: dict = self._data

        atoms: Dict[int, Atom] = data.get('atoms')
        if atoms:
            for ob_id, atom in atoms.items():
                atom.ob_atom_pop()

        bonds: Dict[int, Bond] = data.get('bonds')
        if bonds:
            for ob_idx, bond in bonds.items():
                bond.ob_bond_pop()

        return self._data.pop('ob_obj')

    def ob_mol_rewrap(self, ob_mol: ob.OBMol):
        if not isinstance(ob_mol, ob.OBMol):
            raise TypeError('the ob_mol should be OBMol object')

        atoms = self._data.get('atoms')
        bonds = self._data.get('bonds')

        if any(oba.GetId() not in atoms for oba in ob.OBMolAtomIter(ob_mol)):
            raise ValueError('the atom number between the wrapper and the core OBMol is not match')
        if any(obb.GetId() not in bonds for obb in ob.OBMolBondIter(ob_mol)):
            raise ValueError('the bond number between the wrapper and the core OBMol is not match')

        self._data['ob_obj'] = ob_mol
        for ob_atom in ob.OBMolAtomIter(ob_mol):
            atom = atoms.get(ob_atom.GetId())
            atom.ob_atom_rewrap(ob_atom)

        for ob_bond in ob.OBMolBondIter(ob_mol):
            bond = bonds.get(ob_bond.GetId())
            bond.ob_bond_rewrap(ob_bond)

    @property
    def labels(self):
        return [a.label for a in self.atoms]

    @property
    def lmp(self):
        """ handle to operate the Lammps object """
        return self._data.get('lmp')

    def lmp_close(self):
        pop_lmp = self._data.pop('lmp')
        pop_lmp.close()

    def lmp_setup(self, *args, **kwargs):
        self._data['lmp'] = lmp.HpLammps(self, **kwargs)

    @property
    def link_matrix(self):
        return np.array([[b.ob_atom1_id, b.ob_atom2_id] for b in self.bonds]).T

    def localed_optimize(self, force_field: str = 'UFF', steps: int = 500):
        """ Locally optimize the coordinates. seeing openbabel.pybel package """
        pymol = pb.Molecule(self.ob_mol)
        pymol.localopt(force_field, steps)

    def make_crystal(self, a: float, b: float, c: float, alpha: float, beta: float, gamma: float) -> 'Crystal':
        """ Put this molecule into the specified crystal """
        ob_unit_cell = ob.OBUnitCell()

        self.ob_mol.CloneData(ob_unit_cell)
        self.crystal().ob_unit_cell.SetData(a, b, c, alpha, beta, gamma)
        self.crystal().ob_unit_cell.SetSpaceGroup('P1')

        return self.crystal()

    @property
    def masses(self) -> np.ndarray:
        return np.array([a.mass for a in self.atoms])

    def melt_quench(
            self, elements: Dict[str, float], force_field: Union[str, os.PathLike],
            density: float = 1.0, a: float = 25., b: float = 25., c: float = 25.,
            alpha: float = 90., beta: float = 90., gamma: float = 90., time_step: float = 0.0001,
            origin_temp: float = 298.15, melt_temp: float = 4000., highest_temp: float = 10000.,
            ff_args: Sequence = (), path_writefile: Optional[str] = None, path_dump_to: Optional[str] = None,
            dump_every: int = 100
    ):
        """
        Create a Amorphous crystal materials by performing Melt-Quench process for this materials.
        This process is performed by LAMMPS package, make sure the LAMMPS is accessible.
        A suitable force field is required for the process are performed correctly.
        Args:
            elements(dict[str, float]): Dict of elements and their composition ratio
            force_field(str, os.PathLike): The name of force filed or the path to load a force filed. The name
             of the force filed is refer to the relative path to the 'hotpot_root/data/force_field'.
            density: the demand density for the created amorphous crystal
            a: the length of a vector in the crystal
            b: the length of b vector in the crystal
            c: the length of c vector in the crystal
            alpha: alpha angle of crystal param.
            beta: beta angle of crystal param.
            gamma: gamma angle of crystal param
            time_step: time interval between path integrals when performing melt-quench
            origin_temp: the initial temperature before melt
            melt_temp: the round melting point to the materials
            highest_temp: the highest temperature to liquefy the materials
            ff_args: the arguments the force file requried, refering the LAMMPS pair_coeff:
             "pair_coeff I J args" url: https://docs.lammps.org/pair_coeff.html
            path_writefile: the path to write the final material (screenshot) to file, if not specify, not save.
            path_dump_to:  the path to save the trajectory of the melt-quench process, if not specify not save.
            dump_every: the step interval between each dump operations

        Returns:
            Molecule, a created amorphous material
        """
        return self._melt_quench(
            elements=elements, force_field=force_field, density=density,
            a=a, b=b, c=c, alpha=alpha, beta=beta, gamma=gamma, time_step=time_step,
            origin_temp=origin_temp, melt_temp=melt_temp, highest_temp=highest_temp,
            ff_args=ff_args, path_writefile=path_writefile, path_dump_to=path_dump_to,
            dump_every=dump_every, mol=self
        )

    @property
    def metals(self) -> List['Atom']:
        return [a for a in self.atoms if a.is_metal]

    @property
    def mol_orbital_energies(self):
        energies = self._data.get('mol_orbital_energies')
        if energies:
            return energies
        else:
            return None

    def normalize_labels(self):
        """ Reorder the atoms labels in the molecule """
        element_counts = {}
        for atom in self.atoms:
            count = element_counts.get(atom.symbol, 0)
            count += 1
            element_counts[atom.symbol] = count
            atom.label = f'{atom.symbol}{count}'

    def perturb_mol_lattice(
            self,
            random_style='uniform',
            mol_distance=0.5,
            lattice_fraction=0.05,
            freeze_dim: Sequence[int] = (),
            max_generate_num: int = 10,
            inplace: bool = False
    ) -> Generator["Molecule", None, None]:
        """
        Perturb the coordinate of atom in the mol or the lattice parameters
        generate new mol
        Args:
            random_style: how to sample, 'uniform' or 'normal'
            mol_distance: the max distance of perturbation in 'uniform'; the square variance in 'normal'
            lattice_fraction: the percentage of the lattice perturbation
            freeze_dim: tuple of int or str, 0 = x, 1 = y, 2 = z
            max_generate_num: the maximum of generated molecule
            inplace

        Returns:
            Generator of perturbed molecule
        """
        dim_transform = {'x': 0, 'y': 1, 'z': 2}

        coordinates_shape = (self.atom_num, 3)  # the shape of coordinates matrix (atom counts, 3 dimension)
        origin_coordinates = self.coordinates

        def coordinates_generator():
            """ Generating """
            for _ in range(max_generate_num):
                if random_style == 'uniform':
                    perturb_matrix = np.float64(np.random.uniform(-mol_distance, mol_distance, coordinates_shape))
                elif random_style == 'normal':
                    perturb_matrix = np.float64(np.random.normal(0, mol_distance, coordinates_shape))
                else:
                    raise ValueError('the perturb style is not defined!')

                if freeze_dim:
                    dim = [
                        i if (isinstance(i, int) and 0 <= i <= 3) else dim_transform[i]
                        for i in freeze_dim
                    ]

                    perturb_matrix[:, dim] = 0.

                new_coord = origin_coordinates + perturb_matrix

                yield new_coord

        def lattice_generator():
            """ TODO: this function is prepare to generate the new lattice """

        if inplace:
            origin_all_coordinates = self._data.get('all_coordinates')
            new_all_coordinates = np.array([c for c in coordinates_generator()])

            # TODO: test changes
            if origin_all_coordinates is not None:
                self._data['all_coordinates'] = np.concatenate([origin_all_coordinates, new_all_coordinates])
            else:
                self._data['all_coordinates'] = np.concatenate(
                    [np.reshape(origin_coordinates, (1,) + origin_coordinates.shape), new_all_coordinates]
                )

        else:
            return (self._pert_mol_generate(c) for c in coordinates_generator())

    @property
    def pseudo_atoms(self):
        return self._data.get('pseudo_atoms', [])

    def quick_build_atoms(self, atomic_numbers: np.ndarray):
        """
        This method to quick build atoms according a array of atomic numbers.
        The method bypass to calling more time-consumed method: add_atom().
        However, the method only assign the elements or atomic number for atoms,
        more fine attributes like coordinates, can't be specified.
        Args:
            atomic_numbers(np.ndarray): 1-D numpy array to add new atoms into the molecule

        Returns:
            None
        """
        if not isinstance(atomic_numbers, (np.ndarray, Sequence)):
            raise TypeError('the atomic_numbers should be np.ndarray or Sequence')
        if isinstance(atomic_numbers, np.ndarray) and len(atomic_numbers.shape) != 1:
            raise ValueError('the numpy array must be 1-D')

        for atomic_number in atomic_numbers:
            ob_atom = ob.OBAtom()
            ob_atom.SetAtomicNum(int(atomic_number))
            self.ob_mol.AddAtom(ob_atom)

    @classmethod
    def read_from(cls, source: Union[str, PathLike, IOBase], fmt=None, *args, **kwargs) -> 'Molecule':
        """
        read source to the Molecule obj by call _io.Parser class
        Args:
            source(str, PathLike, IOBase): the formatted source
            fmt:
            *args:
            **kwargs:

        Returns:

        """
        if not fmt:
            if isinstance(source, str):
                source = Path(source)

            if isinstance(source, Path):
                fmt = source.suffix.strip('.')
            else:
                raise ValueError(f'the arguments should be specified for {type(source)} source')

        mol = Parser(fmt, source, *args, **kwargs)()  # initialize parser object and call self

        # Specify the mol identifier if it's None
        if not mol.identifier:
            mol.identifier = str(source)

        return mol

    def register_critical_params(self, name: str, temperature: float, pressure: float, acentric: float):
        """ Register new critical parameters into the critical parameters sheet """
        data = json.load(open(ptj(data_root, 'thermo', 'critical.json')))
        data[self.smiles] = {'name': name, 'temperature': temperature, 'pressure': pressure, 'acentric': acentric}
        with open(ptj(data_root, 'thermo', 'critical.json'), 'w') as writer:
            json.dump(data, writer, indent=True)

    def remove_atoms(self, *atoms: Union[int, str, 'Atom'], remove_hydrogens: bool = False) -> None:
        """
        Remove atom according to given atom index, label or the atoms self.
        Args:
            atoms(int|str|Atom): the index, label or self of Removed atom
            remove_hydrogens(bool): remove the hydrogens connecting in the atoms synchronously.

        Returns:
            None
        """
        # to_remove_bonds = set()
        for atom in atoms:

            # Check and locate the atom
            if isinstance(atom, int):
                atom = self.atoms_dict[atom]
            elif isinstance(atom, str):
                atom = self.atom(atom)
            elif isinstance(atom, Atom):
                if not (atom.molecule is self):
                    raise AttributeError('the given atom not in the molecule')
            else:
                raise TypeError('the given atom should be int, str or Atom')

            # Record the linking bonds with the atom
            # to_remove_bonds.update(atom.bonds)

            # remove connecting hydrogens
            if remove_hydrogens:
                for nh in atom.neighbours_hydrogen:
                    self.ob_mol.DeleteAtom(nh.ob_atom)

            # Removing the atom
            self.ob_mol.DeleteAtom(atom.ob_atom)
            atom._data['mol'] = None

        # Reload atoms
        self._load_atoms()
        self._load_bonds()

    def remove_bonds(self, *bonds: 'Bond'):
        """ Remove the bonds in the molecule """
        for bond in bonds:
            successful = self.ob_mol.DeleteBond(bond.ob_bond)
            if not successful:
                raise RuntimeError(f'Fail to remove {bonds}')

        self._load_bonds()

    def remove_hydrogens(self):
        self.ob_mol.DeleteHydrogens()

    def remove_metals(self):
        """ remove all of metal atoms in the molecule """
        self.remove_atoms(*self.metals)

    def remove_solvents(self):
        """ remove all solvents in the molecule """
        self.normalize_labels()
        for ligand in self.retrieve_ligands():
            if _lib.get('Solvents').is_solvent(ligand):  # To judge if the ligand is solvents
                self.remove_atoms(*ligand.atom_labels, remove_hydrogens=False)

    def retrieve_ligands(self) -> List['Molecule']:
        """ Retrieve all ligand molecule from this """
        clone = self.copy()
        clone.remove_metals()

        return clone.components

    def retrieve_metal_ligand_pairs(self) -> List['Molecule']:
        """ Retrieve all clone of metal-ligand pairs in the molecule """
        if not self.is_labels_unique:
            self.normalize_labels()

        ml_pairs = []
        for metal, ligand in product(self.metals, self.retrieve_ligands()):
            if set(metal.neighbours_label) & set(ligand.atom_labels):
                pair = self.copy()

                # Remove all the atoms is not the metal and not on the ligand
                other_atoms = [a for a in pair.atoms if a.label != metal.label and a.label not in ligand.atom_labels]
                pair.remove_atoms(*other_atoms, remove_hydrogens=False)

                ml_pairs.append(pair)

        return ml_pairs

    @property
    def rotatable_bonds_number(self):
        return self.ob_mol.NumRotors()

    def set(self, **kwargs):
        """ Set the attributes directly """
        self._set_attrs(**kwargs)

    def set_label(self, ob_id: int, label: str):
        self.atoms_dict[ob_id].label = label

    def similarity(self, other: 'Molecule', fptype: Literal['FP2', 'FP3', 'FP4', 'MACCS'] = 'FP2') -> int:
        """
        Compare the similarity with other molecule, based on specified fingerprint
        Args:
            other(Molecule): the other Molecule
            fptype(str): the fingerprint type to perform comparison of similarity

        Return:
            the similarity(int)
        """
        return self.fingerprint(fptype) | other.fingerprint(fptype)

    def smarts(self):
        """ Get the SMARTS string """
        return Chem.MolToSmarts(self.to_rdmol())

    @property
    def smiles(self):
        """ Get the canonical smiles """
        return self.dump('can').split()[0]

    @property
    def spin(self):
        return self.ob_mol.GetTotalSpinMultiplicity()

    @spin.setter
    def spin(self, spin: int):
        self._set_spin_multiplicity(spin)

    def thermo_init(self, **kwargs):
        """
        If certain substance don't retrieve information from current database, some required thermodynamical
        parameters should pass into equation_of_state to initialization
        Keyword Args:
            T: the ambient temperature for thermodynamical system
            P: the ambient pressure for thermodynamical system
            V: the volume of thermodynamical system
            Tc: the critical temperature of the molecule
            Pc: the critical pressure of the molecule
            omega: acentric factor of the molecule

        Returns:
            Thermo class
        """
        from tmo import Thermo
        self._data['thermo'] = Thermo(self, **kwargs)
        return self._data['thermo']

    @property
    def thermo(self):
        return self._data.get('thermo')

    def thermo_close(self):
        _ = self._data.pop('thermo')
        del _

    def to_dpmd_sys(self, dpmd_sys_root: Union[str, os.PathLike], mode: Literal['std', 'att'] = 'std'):
        """
        convert to DeePMD-Kit System, there are two system mode, that `standard` (std) and `attention` (att)
            1) standard: https://docs.deepmodeling.com/projects/deepmd/en/master/data/system.html
            2) attention: https://docs.deepmodeling.com/projects/deepmd/en/master/model/train-se-atten.html#data-format

        Args:
            dpmd_sys_root: the dir for all system data store
            mode: the system mode, choose from att or std
        """
        dpmd_sys_root = Path(dpmd_sys_root)
        if not dpmd_sys_root.exists():
            dpmd_sys_root.mkdir()

        # the dir of set data
        set_root = dpmd_sys_root.joinpath('set.000')
        if not set_root.exists():
            set_root.mkdir()

        data = self.dump('dpmd_sys')

        for name, value in data.items():

            # if the value is None, go to next
            if value is None:
                continue

            # Write the type raw
            if name == 'type':
                if mode == 'std':
                    type_raw = value[0]
                elif mode == 'att':
                    type_raw = np.zeros(value[0].shape, dtype=int)
                    np.save(set_root.joinpath("real_atom_types.npy"), value)
                else:
                    raise ValueError('the mode just allows to be "std" or "att"')

                with open(dpmd_sys_root.joinpath('type.raw'), 'w') as writer:
                    writer.write('\n'.join([str(i) for i in type_raw]))

            elif name == 'type_map':
                with open(dpmd_sys_root.joinpath('type_map.raw'), 'w') as writer:
                    writer.write('\n'.join([str(i) for i in value]))

            # Create an empty 'nopbc', when the system is not periodical
            elif name == 'nopbc' and value is True:
                with open(dpmd_sys_root.joinpath('nopbc'), 'w') as writer:
                    writer.write('')

            # Save the numpy format data
            elif isinstance(value, np.ndarray):
                np.save(set_root.joinpath(f'{name}.npy'), value)

    def to_mix_mol(self):
        return MixSameAtomMol(_data=self._data)

    def to_mol(self):
        return Molecule(_data=self.data)

    def to_rdmol(self):
        """ convert hotpot Molecule object to RdKit mol object """
        return Chem.MolFromMol2Block(self.dump('mol2'))

    @property
    def unique_all_atoms(self):
        return self.unique_atoms + self.unique_pseudo_atoms

    @property
    def unique_atoms(self):
        uni = []
        for a in self.atoms:
            if a not in uni:
                uni.append(a)
        return uni

    @property
    def unique_bonds(self):
        uni = []
        for b in self.bonds:
            if b not in uni:
                uni.append(b)
        return uni

    @property
    def unique_bond_pairs(self) -> List[Tuple[int, int, int]]:
        """ Retrieve unique bond pair in the molecule, i.e. a bond with same atoms element combination and bond type """
        return [b.pair_key for b in self.unique_bonds]

    @property
    def unique_pseudo_atoms(self) -> List['PseudoAtom']:
        uni = []
        for pa in self.pseudo_atoms:
            if pa not in uni:
                uni.append(pa)
        return uni

    @property
    def weight(self):
        return self.ob_mol.GetExactMass()

    def writefile(self, fmt: str, path_file, retrieve_script=False, *args, **kwargs):
        """Write the Molecule Info into a file with specific format(fmt)"""
        script = self.dump(fmt=fmt, *args, **kwargs)
        if isinstance(script, str):
            mode = 'w'
        elif isinstance(script, bytes):
            mode = 'wb'
        else:
            raise IOError(f'the {type(script)} type for script is not supported to write into file')

        with open(path_file, mode) as writer:
            writer.write(script)

        if retrieve_script:
            return script

    @property
    def xyz_min(self) -> np.ndarray:
        """ Return the minimum of x coordinates wreathing all atoms """
        return self.coordinates.min(axis=0)

    @property
    def xyz_max(self) -> np.ndarray:
        return self.coordinates.max(axis=0)

    @property
    def xyz_diff(self):
        return self.xyz_max - self.xyz_min


class MixSameAtomMol(Molecule):
    """ the only difference to the Molecule class is the method of their addition  """

    def __repr__(self):
        return f'MixMol({self.formula})'

    def iadd_accessible(self, other):
        if self.atom_num == other.atom_num:
            return True
        return False


class Atom(Wrapper, ABC):
    """ The Atom wrapper for OBAtom class in openbabel """

    # TODO: to check the consistence of the method to access the OBAtom in OBMol
    # TODO: for atom the correct method to access OBAtom from OBMol is by GetAtomById, not GetAtom !!!
    # TODO: the GetAtomById get OBAtom start from 0
    # TODO: the GetAtom get OBAtom start from 1
    # TODO: the Id of OBAtom start from 0
    # TODO: the Idx of OBAtom start from 1,
    def __init__(
            self,
            ob_atom: ob.OBAtom = None,
            **kwargs
    ):
        # Contain all data to reappear this Atom
        self._data: Dict[str, Any] = {
            'ob_obj': ob_atom if ob_atom else ob.OBAtom(),
        }

        self._set_attrs(**kwargs)

    def __eq__(self, other):
        if isinstance(other, Atom):
            # return self.symbol == other.symbol
            return self.ob_atom == other.ob_atom

    def __hash__(self):
        return hash(f'Atom({self.atomic_number})')

    @property
    def ob_atom(self):
        return self._data['ob_obj']

    @ob_atom.setter
    def ob_atom(self, oba):
        self._data['ob_obj'] = oba

    def ob_atom_pop(self):
        return self._data.pop('ob_obj')

    def ob_atom_rewrap(self, ob_atom):
        self._data['ob_obj'] = ob_atom

    def __repr__(self):
        return f"Atom({self.label if self.label else self.symbol})"

    @property
    def _attr_setters(self) -> Dict[str, Callable]:
        return {
            '_mol': self._set_molecule,
            'mol': self._set_molecule,
            'molecule': self._set_molecule,
            'atomic_number': self._set_atomic_number,
            'symbol': self._set_atomic_symbol,
            'coordinates': self._set_coordinate,
            'formal_charge': self._set_formal_charge,
            'partial_charge': self._set_partial_charge,
            'label': self._set_label,
            'ob_id': self._set_ob_id,
            'spin_density': self._set_spin_density
        }

    def _set_atomic_number(self, atomic_number: int):
        self.ob_atom.SetAtomicNum(int(atomic_number))

    def _set_atomic_symbol(self, symbol):
        atomic_number = periodic_table[symbol]['number']
        self.ob_atom.SetAtomicNum(atomic_number)

    def _set_coordinate(self, coordinates):
        self.ob_atom.SetVector(*coordinates)

    def _set_force_vector(self, force_vector: Union[Sequence, np.ndarray]):
        if isinstance(force_vector, Sequence):
            if all(isinstance(f, float) for f in force_vector):
                force_vector = np.array(force_vector)
            else:
                ValueError('the give force_vector must float vector with dimension 3')
        elif isinstance(force_vector, np.ndarray):
            force_vector = force_vector.flatten()
        else:
            raise TypeError('the force vector should be Sequence or np.ndarray')

        self._data['force_vector'] = force_vector

    def _set_formal_charge(self, charge: float):
        self.ob_atom.SetFormalCharge(charge)

    def _set_ob_id(self, ob_id):
        self.ob_atom.SetId(ob_id)

    def _set_label(self, label):
        label_data = ob.OBCommentData()

        label_data.SetAttribute('label')
        label_data.SetData(label)

        self.ob_atom.CloneData(label_data)

    def _set_molecule(self, molecule: Molecule):
        self._data['mol'] = molecule

    def _set_partial_charge(self, charge):
        self.ob_atom.SetPartialCharge(charge)

    def _set_spin_density(self, spin_density: float):
        self._data['spin_density'] = spin_density

    @property
    def atom_type(self):
        """ Some atom have specific type, such as Carbon with sp1, sp2 and sp3, marked as C1, C2 and C3 """
        return self.ob_atom.GetType()

    def add_atom(self, symbol: str, bond_type=1, **atom_attrs):
        """ add atom to link with this atom """
        new_atom = self.molecule.add_atom(symbol, **atom_attrs)
        self.molecule.add_bond(self, new_atom, bond_type)

    @property
    def atomic_number(self):
        return self.ob_atom.GetAtomicNum()

    @property
    def bond_valence(self) -> int:
        return sum(b.type for b in self.bonds)

    @property
    def bonds(self):
        """ Get all bonds link with the atoms """
        return [self.molecule.bonds_dict[obb.GetId()] for obb in ob.OBAtomBondIter(self.ob_atom)]

    @property
    def coordinates(self) -> (float, float, float):
        return self.ob_atom.GetX(), self.ob_atom.GetY(), self.ob_atom.GetZ()

    @coordinates.setter
    def coordinates(self, value):
        self._set_coordinate(value)

    @property
    def coordinates_array(self) -> np.ndarray:
        """ the array of coordinates """
        return np.array(self.coordinates)

    def copy(self):
        """ Make a copy of self """
        # Extract old data
        data = self.data
        data.pop('ob_obj')  # Remove the old OBAtom
        # Remove molecule if the parent atom in a molecule
        if self.molecule:
            data.pop('mol')

        # Copy the information contained in OBAtom
        new_attrs = {
            "atomic_number": self.atomic_number,
            "coordinates": self.coordinates,
            'partial_charge': self.partial_charge,
            # 'label': self.label,
            # 'ob_id': self.ob_id
        }

        new_attrs.update(**data)

        return Atom(**new_attrs)

    def element_features(self, *feature_names) -> np.ndarray:
        """ Retrieve the feature vector """
        atom_feature = periodic_table.get(self.symbol)

        features = []
        for feature_name in feature_names:
            if feature_name == 'atomic_orbital':
                features.extend(self._atomic_orbital_feature().values())
            elif feature_name == 'atomic_number':
                features.append(self.atomic_number)
            else:
                features.append(atom_feature[feature_name])

        return np.array(features)

    def _atomic_orbital_feature(self, outermost_layer=True, nonexistent_orbit=0):
        """    Calculating the feature about atomic orbital structures    """
        _atomic_orbital_structure_max = {
            "1s": 2,
            "2s": 2, "2p": 6,
            "3s": 2, "3p": 6,
            "4s": 2, "3d": 10, "4p": 6,
            "5s": 2, "4d": 10, "5p": 6,
            "6s": 2, "4f": 14, "5d": 10, "6p": 6,
            "7s": 2, "5f": 14, "6d": 10, "7p": 6
        }
        atomic_orbital_structure = {
            "1s": 0,
            "2s": 0, "2p": 0,
            "3s": 0, "3p": 0,
            "4s": 0, "3d": 0, "4p": 0,
            "5s": 0, "4d": 0, "5p": 0,
            "6s": 0, "4f": 0, "5d": 0, "6p": 0,
            "7s": 0, "5f": 0, "6d": 0, "7p": 0
        }

        # Calculating atomic orbital structure
        residual_electron = self.atomic_number
        n_osl = 0  # Principal quantum number (n) of open shell layers (osl)
        for orbital_name, men in _atomic_orbital_structure_max.items():  # max electron number (men)

            # Update Principal quantum number (n)
            if orbital_name[1] == "s":
                n_osl = int(orbital_name[0])

            # Filled atomic orbital
            if residual_electron - men >= 0:
                residual_electron = residual_electron - men
                atomic_orbital_structure[orbital_name] = men
            else:
                atomic_orbital_structure[orbital_name] = residual_electron
                break

        # Readout and return outermost electron structure
        atom_orbital_feature = {"atomic_number": self.atomic_number, "n_osl": n_osl}
        if outermost_layer:
            diff_max_n = {"s": 0, "p": 0, "d": -1, "f": -2}
            for layer, diff in diff_max_n.items():  # Angular momentum quantum number (l)
                electron_number = atomic_orbital_structure.get(f"{n_osl + diff}{layer}", nonexistent_orbit)
                atom_orbital_feature[layer] = electron_number
        else:
            atom_orbital_feature.update(atomic_orbital_structure)

        # return whole electron structure directly
        return atom_orbital_feature

    @property
    def force_vector(self):
        return self._data.get('force_vector', np.zeros(3, dtype=float))

    @force_vector.setter
    def force_vector(self, force_vector: Union[Sequence, np.ndarray]):
        self._set_force_vector(force_vector)

    @property
    def formal_charge(self) -> float:
        return self.ob_atom.GetFormalCharge()

    @formal_charge.setter
    def formal_charge(self, value: float):
        self.ob_atom.SetFormalCharge(value)

    @property
    def hybridization(self):
        """ The hybridization of this atom:
        1 for sp, 2 for sp2, 3 for sp3, 4 for sq. planar, 5 for trig. bipy, 6 for octahedral """
        return self.ob_atom.GetHyb()

    @property
    def kwargs_attributes(self):
        return tuple(self._attr_setters.keys())

    @property
    def ob_id(self):
        return self.ob_atom.GetId()

    @property
    def ob_idx(self):
        return self.ob_atom.GetIdx()

    @property
    def is_aromatic(self):
        return self.ob_atom.IsAromatic()

    @property
    def is_chiral(self):
        return self.ob_atom.IsChiral()

    @property
    def is_hydrogen(self):
        return self.ob_atom.GetAtomicNum() == 1

    @property
    def is_polar_hydrogen(self) -> bool:
        """ Is this atom a hydrogen connected to a polar atom """
        return self.ob_atom.IsPolarHydrogen()

    @property
    def is_metal(self):
        return self.ob_atom.IsMetal()

    @property
    def label(self):
        label_data = self.ob_atom.GetData('label')

        if label_data:
            label_data = ob.toCommentData(label_data)
            return label_data.GetValue()
        else:
            return self.symbol

    @label.setter
    def label(self, value):
        self._set_label(value)

    @property
    def link_degree(self) -> int:
        """ the degree of the atom in their parent molecule """
        return self.ob_atom.GetTotalDegree()

    @property
    def mass(self):
        return self.ob_atom.GetAtomicMass()

    @property
    def max_total_bond_order(self):
        return _max_total_bond_order[self.symbol]

    @property
    def molecule(self) -> Molecule:
        return self._data.get('mol')

    @molecule.setter
    def molecule(self, mol: 'Molecule'):
        self._data['mol'] = mol

    @property
    def neighbours_hydrogen(self) -> List['Atom']:
        """ return all neigh hydrogen atoms """
        return [a for a in self.neighbours if a.is_hydrogen]

    @property
    def neighbours(self) -> List['Atom']:
        """ Get all atoms bond with this atom in same molecule """
        if self.molecule:
            _ = self.molecule.atoms  # update the atoms dict
            return [self.molecule.atoms_dict[ob_atom.GetId()] for ob_atom in ob.OBAtomAtomIter(self.ob_atom)]
        else:
            return []

    @property
    def neighbours_label(self) -> List[str]:
        """ return all neighbours labels """
        return [a.label for a in self.neighbours]

    @property
    def neighbours_position(self) -> Generator[Tuple[Union['Atom', np.ndarray]], None, None]:
        """ Retrieve the relative position of neigh atoms, assign this atom as the origin """
        for neigh_atom in self.neighbours:
            yield neigh_atom, neigh_atom.coordinates_array - self.coordinates_array

    @property
    def partial_charge(self):
        return self.ob_atom.GetPartialCharge()

    def remove_redundant_hydrogen(self):
        """ Remove hydrogens link with this atom, if the bond valence is more than the max allowed valence"""
        if self.is_hydrogen:
            return None

        # remove redundant hydrogen
        while self.bond_valence > abs(self.valence_max) and self.neighbours_hydrogen:
            self.molecule.remove_atoms(self.neighbours_hydrogen[0])
            self.formal_charge += self.formal_charge - 1

    @partial_charge.setter
    def partial_charge(self, value: float):
        # This is necessary to take effect to the assignment.
        # the reason is unknown
        self.ob_atom.GetPartialCharge()
        self._set_partial_charge(value)

    def replace_attr_data(self, data: Dict):
        """ Replace the core data dict directly """
        self._data = data

    def set(self, **kwargs):
        """
        Set atom attributes by kwargs
        Kwargs:
            atomic_number(int): set atomic number
            symbol(str): set atomic symbol
            coordinates(Sequence, numpy.ndarray): coordinates of the atom
            partial_charge:
            label:
            spin_density:
        """
        self._set_attrs(**kwargs)  # set attributes

    @property
    def spin_density(self):
        return self._data.get('spin_density', 0.0)

    @spin_density.setter
    def spin_density(self, spin_density: float):
        self._set_spin_density(spin_density)

    @property
    def stable_valence(self) -> int:
        return _stable_charges.get(self.symbol, None)

    @property
    def symbol(self) -> str:
        return _symbols[self.atomic_number]

    @property
    def valence(self) -> int:
        """ The current number of explicit connections """
        return self.ob_atom.GetTotalValence()

    @property
    def valence_max(self) -> int:
        """ The implicit valence of this atom type (i.e. maximum number of connections expected) """
        return _max_valences[self.symbol]


class PseudoAtom(Wrapper, ABC):
    """ A data wrapper for pseudo atom """

    def __init__(self, symbol: str, mass: float, coordinates: Union[Sequence, np.ndarray], **kwargs):
        if isinstance(coordinates, Sequence):
            coordinates = np.array(coordinates)

        assert isinstance(coordinates, np.ndarray) and coordinates.shape == (3,)

        self._data = dict(symbol=symbol, mass=mass, coordinates=coordinates, **kwargs)

    def __eq__(self, other):
        if isinstance(other, PseudoAtom):
            return self.symbol == other.symbol
        return False

    def __hash__(self):
        return hash(f'PseudoAtom({self.symbol})')

    def _attr_setters(self) -> Dict[str, Callable]:
        return {}

    def __repr__(self):
        return f'PseudoAtom({self.symbol})'

    def __dir__(self) -> Iterable[str]:
        return list(self._data.keys())

    def __getattr__(self, item):
        return self._data.get(item, 0.)


class Bond(Wrapper, ABC):
    """"""

    def __init__(self, ob_bond: ob.OBBond, _mol: Molecule):
        self._data = {
            'ob_obj': ob_bond,
            'mol': _mol
        }

    def __repr__(self):
        return f"Bond({self.atoms[0].label}, {self.atoms[1].label}, {self.type_name})"

    def __eq__(self, other: 'Bond'):
        if isinstance(other, Bond):
            return self.pair_key == other.pair_key

    def __hash__(self):
        return hash(self.pair_key)

    @property
    def ob_bond(self):
        return self._data['ob_obj']

    def ob_bond_pop(self):
        return self._data.pop('ob_obj')

    def ob_bond_rewrap(self, ob_bond):
        self._data['ob_obj'] = ob_bond

    @property
    def _attr_setters(self) -> Dict[str, Callable]:
        return {
        }

    @property
    def atom1(self) -> Atom:
        return self.molecule.atoms_dict[self.ob_atom1_id]

    @property
    def atom2(self) -> Atom:
        return self.molecule.atoms_dict[self.ob_atom2_id]

    @property
    def atomic_number1(self):
        return self.ob_bond.GetBeginAtom().GetAtomicNum()

    @property
    def atomic_number2(self):
        return self.ob_bond.GetEndAtom().GetAtomicNum()

    @property
    def atoms(self):
        return self.atom1, self.atom2

    @property
    def begin_end_ob_id(self) -> (int, int):
        return self.ob_bond.GetBeginAtom().GetId(), self.ob_bond.GetEndAtom().GetId()

    @property
    def begin_end_atomic_number(self):
        return self.ob_bond.GetBeginAtom().GetAtomicNum(), self.ob_bond.GetEndAtom().GetAtomicNum()

    @property
    def ideal_length(self):
        return self.ob_bond.GetEquibLength()

    @property
    def ob_id(self):
        return self.ob_bond.GetId()

    @property
    def ob_idx(self):
        return self.ob_bond.GetIdx()

    @property
    def ob_atom1(self):
        return self.ob_bond.GetBeginAtom()

    @property
    def ob_atom2(self):
        return self.ob_bond.GetEndAtom()

    @property
    def ob_atom1_id(self):
        return self.ob_atom1.GetId()

    @property
    def ob_atom2_id(self):
        return self.ob_atom2.GetId()

    @property
    def pair_key(self):
        """ Get the bond pair key, a string that show combination of element of end atoms and bond type,
        where, the atomic symbol with lower atomic number is placed in the first, the higher in the last"""
        if self.atomic_number1 <= self.atomic_number2:
            return self.atomic_number1, self.type, self.atomic_number2
        return self.atomic_number2, self.type, self.atomic_number1

    @property
    def length(self):
        return self.ob_bond.GetLength()

    @property
    def molecule(self):
        return self._data['mol']

    @molecule.setter
    def molecule(self, mol: Molecule):
        self._data['mol'] = mol

    @property
    def type_name(self):
        return _type_bond[self.type]

    @property
    def type(self):
        return self.ob_bond.GetBondOrder()


class Angle:
    """ Data wrapper of angle in molecule """

    def __init__(self, mol: 'Molecule', atoms_ob_id: tuple):
        self._data = {
            'mol': mol,
            'atoms_ob_id': atoms_ob_id
        }

    def __repr__(self):
        a, b, c = self.atoms
        return f'Angle({a.label}, {b.label}, {c.label}, {round(self.degree, 2)}°)'

    @property
    def molecule(self):
        return self._data.get('mol')

    @molecule.setter
    def molecule(self, mol: Molecule):
        self._data['mol'] = mol

    @property
    def atoms(self):
        mas = self.molecule.atoms  # atom in the molecule
        return [mas[i] for i in self.atoms_ob_id]

    @property
    def atoms_ob_id(self):
        return self._data.get('atoms_ob_id')

    @property
    def degree(self):
        ob_atoms = [a.ob_atom for a in self.atoms]
        return self.molecule.ob_mol.GetAngle(*ob_atoms)


class Crystal(Wrapper, ABC):
    """"""
    _lattice_type = (
        'Undefined', 'Triclinic', 'Monoclinic', 'Orthorhombic', 'Tetragonal', 'Rhombohedral', 'Hexagonal', 'Cubic'
    )

    def __init__(self, ob_unitcell: ob.OBUnitCell = None, **kwargs):

        self._data: Dict[str, Any] = {
            'OBUnitCell': ob_unitcell if ob_unitcell else ob.OBUnitCell(),
        }

        self._set_attrs(**kwargs)

    def __repr__(self):
        return f'Crystal({self.lattice_type}, {self.space_group}, {self.molecule})'

    @property
    def ob_unit_cell(self) -> ob.OBUnitCell:
        return self._data.get('OBUnitCell')

    @staticmethod
    def _matrix_to_params(matrix: np.ndarray):
        """ Covert the cell matrix to cell parameters: a, b, c, alpha, beta, gamma """
        va, vb, vc = matrix
        a = sum(va ** 2) ** 0.5
        b = sum(vb ** 2) ** 0.5
        c = sum(vc ** 2) ** 0.5

        alpha = np.arccos(np.dot(va, vb) / (a * b)) / np.pi * 180
        beta = np.arccos(np.dot(va, vc) / (a * c)) / np.pi * 180
        gamma = np.arccos(np.dot(vb, vc) / (b * c)) / np.pi * 180

        return a, b, c, alpha, beta, gamma

    def _set_molecule(self, molecule: Molecule):
        if molecule.crystal and isinstance(molecule.crystal, Crystal):
            print(AttributeError("the Molecule have been stored in a Crystal, "
                                 "can't save the same Molecule into two Crystals"))
        else:
            self._data['mol'] = molecule

    def _set_space_group(self, space_group: str):
        self.ob_unit_cell.SetSpaceGroup(space_group)

    @property
    def _attr_setters(self) -> Dict[str, Callable]:
        return {
            'mol': self._set_molecule,
            'molecule': self._set_molecule,
            'space_group': self._set_space_group
        }

    @property
    def lattice_type(self) -> str:
        return self._lattice_type[self.ob_unit_cell.GetLatticeType()]

    @property
    def lattice_params(self) -> np.ndarray[2, 3]:
        a = self.ob_unit_cell.GetA()
        b = self.ob_unit_cell.GetB()
        c = self.ob_unit_cell.GetC()
        alpha = self.ob_unit_cell.GetAlpha()
        beta = self.ob_unit_cell.GetBeta()
        gamma = self.ob_unit_cell.GetGamma()
        return np.array([[a, b, c], [alpha, beta, gamma]])

    @property
    def molecule(self) -> Molecule:
        return self._data.get('mol')

    @molecule.setter
    def molecule(self, mol: Molecule):
        self._data['mol'] = mol

    @property
    def pack_molecule(self) -> Molecule:
        mol = self.molecule  # Get the contained Molecule

        if not mol:  # If get None
            print(RuntimeWarning("the crystal doesn't contain any Molecule!"))

        pack_mol = mol.copy()
        self.ob_unit_cell.FillUnitCell(pack_mol.ob_mol)  # Full the crystal
        pack_mol._reorganize_atom_indices()  # Rearrange the atom indices.

        return pack_mol

    def set_lattice(
            self,
            a: float, b: float, c: float,
            alpha: float, beta: float, gamma: float
    ):
        self.ob_unit_cell.SetData(a, b, c, alpha, beta, gamma)

    def set_vectors(
            self,
            va: Union[np.ndarray, Sequence],
            vb: Union[np.ndarray, Sequence],
            vc: Union[np.ndarray, Sequence]
    ):
        """"""
        vectors = [va, vb, vc]
        matrix = np.array(vectors)
        self.set_matrix(matrix)

    def set_matrix(self, matrix: np.ndarray):
        """ Set cell matrix for the crystal """
        if matrix.shape != (3, 3):
            raise AttributeError('the shape of cell_vectors should be [3, 3]')

        cell_params = map(float, self._matrix_to_params(matrix))

        self.ob_unit_cell.SetData(*cell_params)

    @property
    def space_group(self):
        space_group = self.ob_unit_cell.GetSpaceGroup()
        if space_group:
            return space_group.GetHMName()
        else:
            return None

    @space_group.setter
    def space_group(self, value: str):
        self._set_space_group(value)

    @property
    def volume(self):
        return self.ob_unit_cell.GetCellVolume()

    @property
    def vector(self):
        v1, v2, v3 = self.ob_unit_cell.GetCellVectors()
        return np.array([
            [v1.GetX(), v1.GetY(), v1.GetZ()],
            [v2.GetX(), v2.GetY(), v2.GetZ()],
            [v3.GetX(), v3.GetY(), v3.GetZ()]
        ])

    def zeo_plus_plus(self):
        """ TODO: complete the method after define the Crystal and ZeoPlusPlus tank """


import hotpot.bundle as bd
from hotpot._io import Dumper, Parser
from hotpot.tanks.cc import PairBundle
