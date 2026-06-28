"""Tests for rizza.genetics."""
from rizza.helpers import genetics

BASE_GENOME = list(range(25))
NESTED_GENOME = [[8, 11, 55, 76, 99], [4, 66, 74, 83, 92], [3, 16, 25, 34, 57]]
DEFAULT_POP_COUNT = 20
DEFAULT_GEN_COUNT = 100


def grade_single_list(submitted, genome=BASE_GENOME):
    result = 0
    for i in range(len(genome)):
        result += abs(genome[i] - submitted[i]) * (25 - i)
    return result**3  # we exponentially favor more desired results


def grade_nested_list(submitted):
    result = 0
    for i in range(len(submitted)):
        result += grade_single_list(submitted[i], NESTED_GENOME[i])
    return result


def test_positive_create_population():
    test_pop = genetics.Population(gene_base=BASE_GENOME)
    assert test_pop.population_count == DEFAULT_POP_COUNT
    assert not test_pop.rev_pop_sort
    assert len(test_pop.population) == DEFAULT_POP_COUNT
    org_0 = test_pop.population[0]
    org_1 = test_pop.population[1]
    # This assertion has a 1:3628800 chance of failing
    assert org_0.genes != org_1.genes
    assert org_0.points == 0


def test_positive_create_nested_population():
    test_pop = genetics.Population(gene_base=NESTED_GENOME)
    assert test_pop.population_count == DEFAULT_POP_COUNT
    assert len(test_pop.population) == DEFAULT_POP_COUNT
    org_0 = test_pop.population[0]
    assert len(org_0.genes) == 3  # (no magic numbers)
    assert isinstance(org_0.genes[0], list)


def test_positive_reach_goal():
    """Create a population and breed them until one matches"""
    test_pop = genetics.Population(gene_base=BASE_GENOME, population_count=10)
    for i in range(10):
        test_pop.population[i].points = grade_single_list(test_pop.population[i].genes)
    test_pop.sort_population()
    initial_points = test_pop.population[0].points
    generations = 1
    while test_pop.population[0].points > 0 and generations < DEFAULT_GEN_COUNT:
        test_pop.breed_population()
        assert len(test_pop.population) == test_pop.population_count
        generations += 1
        for i in range(10):
            test_pop.population[i].points = grade_single_list(test_pop.population[i].genes)
    test_pop.sort_population()
    assert test_pop.population[0].points < initial_points


def test_positive_nested_reach_goal():
    """Create a population and breed them until one matches"""
    test_pop = genetics.Population(gene_base=NESTED_GENOME, population_count=10)
    for i in range(10):
        test_pop.population[i].points = grade_nested_list(test_pop.population[i].genes)
    test_pop.sort_population()
    initial_points = test_pop.population[0].points
    generations = 1
    while test_pop.population[0].points > 0 and generations < DEFAULT_GEN_COUNT:
        test_pop.breed_population()
        assert len(test_pop.population) == test_pop.population_count
        generations += 1
        for i in range(10):
            test_pop.population[i].points = grade_nested_list(test_pop.population[i].genes)
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


# ── New mechanism tests ────────────────────────────────────────────────────────

TWO_LIST_GENOME = [["p1", "p2", "p3"], ["i1", "i2", "i3"]]


def test_correlated_crossover_preserves_pairing():
    """Crossover on 2-list genes must use the same point for both sublists."""
    pop = genetics.Population(gene_base=TWO_LIST_GENOME[:])
    parent1 = genetics.Organism(genes=[["a", "b", "c"], ["x", "y", "z"]])
    parent2 = genetics.Organism(genes=[["d", "e", "f"], ["u", "v", "w"]])

    for _ in range(50):
        child = pop._breed_pair(parent1.genes, parent2.genes)
        # The child must still be a 2-list
        assert len(child) == 2
        # Both sublists must have the same length
        assert len(child[0]) == len(child[1])
        # Each position must come from the same parent in both sublists
        for i in range(len(child[0])):
            from_parent1 = child[0][i] in ["a", "b", "c"]
            from_parent1_input = child[1][i] in ["x", "y", "z"]
            # Either both from parent1 or both from parent2
            assert from_parent1 == from_parent1_input


def test_uniform_crossover():
    """Uniform crossover produces valid offspring with correct sublist correspondence."""
    pop = genetics.Population(gene_base=TWO_LIST_GENOME[:], crossover_method="uniform")
    parent1 = genetics.Organism(genes=[["a", "b", "c"], ["x", "y", "z"]])
    parent2 = genetics.Organism(genes=[["d", "e", "f"], ["u", "v", "w"]])

    for _ in range(20):
        child = pop._breed_pair(parent1.genes, parent2.genes)
        assert len(child) == 2
        assert len(child[0]) == len(child[1])
        for i in range(len(child[0])):
            assert child[0][i] in ("a", "b", "c", "d", "e", "f")
            assert child[1][i] in ("x", "y", "z", "u", "v", "w")


def test_variable_length_crossover():
    """Crossover of 2-list genes with different lengths stays paired."""
    pop = genetics.Population(gene_base=TWO_LIST_GENOME[:])
    parent1 = genetics.Organism(genes=[["a", "b", "c"], ["x", "y", "z"]])
    parent2 = genetics.Organism(genes=[["d", "e"], ["u", "v"]])

    for _ in range(50):
        child = pop._breed_pair(parent1.genes, parent2.genes)
        assert len(child) == 2
        assert len(child[0]) == len(child[1])
        assert len(child[0]) >= 1


def test_tournament_selection():
    """Tournament selection returns the fittest contestant."""
    pop = genetics.Population(gene_base=BASE_GENOME, population_count=10, rev_pop_sort=False)
    for i, org in enumerate(pop.population):
        org.points = i  # ascending: org 0 is best (minimising)

    for _ in range(20):
        winner = pop._tournament_select(tournament_size=3)
        # In minimise mode the winner should have a lower score than the average
        assert winner.points < 7  # average is 4.5; a random winner won't always be the best


def test_elitism_preserves_best():
    """Elite organisms survive unchanged into the next generation."""
    pop = genetics.Population(gene_base=BASE_GENOME, population_count=10)
    for _, org in enumerate(pop.population):
        org.points = grade_single_list(org.genes)
    pop.sort_population()
    best_genes_before = [g for g in pop.population[0].genes]
    pop.breed_population(elite_percentage=20)  # 20% of 10 = 2 elites
    # After breeding the new population should contain the original best genes
    all_genes = [org.genes for org in pop.population]
    assert best_genes_before in all_genes


def test_immigration_injects_fresh_organisms():
    """breed_population injects immigration_rate% fresh random organisms."""
    pop = genetics.Population(gene_base=BASE_GENOME, population_count=20)
    for org in pop.population:
        org.points = 0  # uniform scores → diversity will be low

    # Collect gene sets before breeding
    genes_before = {tuple(org.genes) for org in pop.population}
    pop.breed_population(immigration_rate=20)  # 20% of 20 = 4 immigrants
    genes_after = {tuple(org.genes) for org in pop.population}
    # At least some genes should differ (immigrants introduce new material)
    assert genes_before != genes_after


def test_adaptive_mutation_low_diversity():
    """Low diversity triggers high mutation rate."""
    # 20 organisms, 1 unique score → diversity = 1/20 = 0.05 < 0.1
    pop = genetics.Population(gene_base=BASE_GENOME, population_count=20)
    for org in pop.population:
        org.points = 42
    assert pop._compute_mutation_chance() == 0.8


def test_adaptive_mutation_high_diversity():
    """High diversity uses base mutation rate."""
    pop = genetics.Population(gene_base=BASE_GENOME, population_count=10)
    for i, org in enumerate(pop.population):
        org.points = i * 100  # all unique → diversity = 1.0
    assert pop._compute_mutation_chance() == 0.2


def test_stagnation_restart():
    """Partial restart fires after population_count*2 generations without improvement."""
    pop = genetics.Population(gene_base=BASE_GENOME, population_count=5, mutate=False)
    for org in pop.population:
        org.points = 100

    # The restart fires exactly on the threshold-th consecutive bad generation.
    # Each breed_population() call increments the counter; when it reaches
    # population_count*2 the restart fires and counter resets to 0 within that call.
    threshold = pop.population_count * 2
    for _ in range(threshold):
        pop.breed_population()
        for org in pop.population:
            org.points = 100

    assert pop._stagnation_counter == 0
    assert len(pop.population) == pop.population_count


def test_variable_length_gene_add():
    """The add mutation operator appends a new param+input pair."""
    available = ["p1", "p2", "p3"]
    type_pools = {"p2": ["i2a", "i2b"], "p3": ["i3a"]}
    # Force many mutations; at least one add should fire
    added = False
    for _ in range(200):
        test_org = genetics.Organism(genes=[["p1"], ["i1"]])
        original_len = len(test_org.genes[0])
        test_org.mutate(available_genes=available, type_pools=type_pools)
        if len(test_org.genes[0]) > original_len:
            # Verify pairing is still intact
            assert len(test_org.genes[0]) == len(test_org.genes[1])
            assert test_org.genes[0][-1] in available
            added = True
            break
    assert added, "Add operator never fired in 200 attempts"


def test_variable_length_gene_remove():
    """The remove mutation operator drops a pair; floors at length 1."""
    removed = False
    for _ in range(200):
        test_org = genetics.Organism(genes=[["p1", "p2", "p3"], ["i1", "i2", "i3"]])
        original_len = len(test_org.genes[0])
        test_org.mutate(available_genes=["p1", "p2", "p3"])
        if len(test_org.genes[0]) < original_len:
            assert len(test_org.genes[0]) == len(test_org.genes[1])
            removed = True
            break
    assert removed, "Remove operator never fired in 200 attempts"


def test_variable_length_gene_floor():
    """Remove operator never shrinks a 1-element gene below length 1."""
    for _ in range(500):
        test_org = genetics.Organism(genes=[["p1"], ["i1"]])
        test_org.mutate(available_genes=["p1"])
        assert len(test_org.genes[0]) >= 1
        assert len(test_org.genes[1]) >= 1
