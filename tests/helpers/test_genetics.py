# -*- encoding: utf-8 -*-
"""Tests for rizza.genetics."""
import pytest
from rizza.helpers import genetics

BASE_GENOME = [15, 22, 6, 31, 10, 5, 93, 67, 88, 59]
NESTED_GENOME = [
    [8, 11, 55, 76, 99],
    [4, 66, 74, 83, 92],
    [3, 16, 25, 34, 57]
]


def grade_single_list(submitted, genome=BASE_GENOME):
    result = 0
    for i in range(len(genome)):
        result += abs(genome[i] - submitted[i]) * (10 - i)
    return result ** 3  # we exponentially favor more desired results


def grade_nested_list(submitted):
    result = 0
    for i in range(len(submitted)):
        result += grade_single_list(submitted[i], NESTED_GENOME[i])
    return result


def test_positive_create_population():
    test_pop = genetics.Population(gene_base=BASE_GENOME)
    assert test_pop.population_count == 20
    assert not test_pop.rev_pop_sort
    assert len(test_pop.population) == 20
    org_0 = test_pop.population[0]
    org_1 = test_pop.population[1]
    # This assertion has a 1:3628800 chance of failing
    assert org_0.genes != org_1.genes
    assert org_0.points == 0


def test_positive_create_nested_population():
    test_pop = genetics.Population(gene_base=NESTED_GENOME)
    assert test_pop.population_count == 20
    assert len(test_pop.population) == 20
    org_0 = test_pop.population[0]
    assert len(org_0.genes) == 3
    assert isinstance(org_0.genes[0], list)


def test_positive_reach_goal():
    """Create a population and breed them until one matches """
    test_pop = genetics.Population(
        gene_base=BASE_GENOME, population_count=10)
    for i in range(10):
        test_pop.population[i].points = grade_single_list(
            test_pop.population[i].genes
        )
    test_pop.sort_population()
    initial_points = test_pop.population[0].points
    generations = 1
    while test_pop.population[0].points > 0 and generations < 100:
        test_pop.breed_population()
        assert len(test_pop.population) == test_pop.population_count
        generations += 1
        for i in range(10):
            test_pop.population[i].points = grade_single_list(
                test_pop.population[i].genes
            )
    test_pop.sort_population()
    assert test_pop.population[0].points < initial_points


def test_positive_nested_reach_goal():
    """Create a population and breed them until one matches """
    test_pop = genetics.Population(
        gene_base=NESTED_GENOME, population_count=10)
    for i in range(10):
        test_pop.population[i].points = grade_nested_list(
            test_pop.population[i].genes
        )
    test_pop.sort_population()
    initial_points = test_pop.population[0].points
    generations = 1
    while test_pop.population[0].points > 0 and generations < 100:
        test_pop.breed_population()
        assert len(test_pop.population) == test_pop.population_count
        generations += 1
        for i in range(10):
            test_pop.population[i].points = grade_nested_list(
                test_pop.population[i].genes
            )
    test_pop.sort_population()
    assert test_pop.population[0].points < initial_points


def test_positive_organism():
    test_org = genetics.Organism(genes=BASE_GENOME)
    assert test_org.genes == BASE_GENOME
    test_org.generate_genes()
    # This assertion has a 1:3628800 chance of failing
    assert test_org.genes != BASE_GENOME
    previous = test_org.genes[:]
    # We will make the mutation chance 100% to force a mutation
    test_org.mutate(gene_base=BASE_GENOME, mutation_chance=1)
    assert test_org.genes != previous


def test_positive_nested_organism():
    test_org = genetics.Organism(genes=NESTED_GENOME)
    assert test_org.genes == NESTED_GENOME
    test_org.generate_genes()
    # This assertion has a 1:3628800 chance of failing
    assert test_org.genes != NESTED_GENOME
    previous = [gene[:] for gene in test_org.genes]
    # We will make the mutation chance 100% to force a mutation
    test_org.mutate(gene_base=NESTED_GENOME, mutation_chance=1)
    assert test_org.genes != previous
