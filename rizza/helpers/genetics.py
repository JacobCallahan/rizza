"""Genetic algorithm base classes."""
import copy
import random

import attr


@attr.s()
class Population:
    """This class is the controller for the population of Organisms."""

    gene_base = attr.ib(validator=attr.validators.instance_of(list), cmp=False, repr=False)
    population_count = attr.ib(default=20)
    population = attr.ib(default=attr.Factory(list), cmp=False)
    rev_pop_sort = attr.ib(default=False, cmp=False, repr=False)
    generator_function = attr.ib(default=False, cmp=False, repr=False)
    gene_length = attr.ib(default=False, cmp=False, repr=False)
    mutate = attr.ib(default=True, cmp=False, repr=False)
    crossover_method = attr.ib(default="single_point", cmp=False, repr=False)

    def __attrs_post_init__(self):
        """Generate a population of organisms."""
        self._best_score = None
        self._stagnation_counter = 0
        self.population = []
        for _ in range(self.population_count):
            org = Organism(genes=self.gene_base[:])
            org.generate_genes(gen_func=self.generator_function, count=self.gene_length)
            self.population.append(org)

    def _breed_pair(self, gene_list1, gene_list2):
        """Breed two gene lists using correlated crossover.

        For nested genes, a single crossover point is shared across all sublists to preserve
        positional correspondence (e.g. param_names[i] stays paired with param_inputs[i]).
        Variable-length sublists: extra pairs from the longer parent are included with 50% chance.
        """
        if not gene_list1 or not gene_list2:
            return list(gene_list1 or gene_list2)

        if isinstance(gene_list1[0], list):
            min_len = min(len(gene_list1[0]), len(gene_list2[0]))
            longer_len = max(len(gene_list1[0]), len(gene_list2[0]))
            # Precompute inclusion decisions for extra pairs — same flip applied to all sublists
            # so corresponding positions stay paired.
            include_extra = [random.random() < 0.5 for _ in range(longer_len - min_len)]

            if self.crossover_method == "uniform":
                # Per-position coin flip, same flip applied across all sublists
                flips = [random.random() < 0.5 for _ in range(min_len)]
                new_gene_list = []
                for sub1, sub2 in zip(gene_list1, gene_list2, strict=False):
                    child = [sub1[i] if flips[i] else sub2[i] for i in range(min_len)]
                    longer = sub1 if len(sub1) > len(sub2) else sub2
                    for j, keep in enumerate(include_extra):
                        if keep:
                            child.append(longer[min_len + j])
                    new_gene_list.append(child)
            else:
                crossover = random.randint(0, min_len)
                new_gene_list = []
                for sub1, sub2 in zip(gene_list1, gene_list2, strict=False):
                    child = sub1[:crossover] + sub2[crossover:min_len]
                    longer = sub1 if len(sub1) > len(sub2) else sub2
                    for j, keep in enumerate(include_extra):
                        if keep:
                            child.append(longer[min_len + j])
                    new_gene_list.append(child)
            return new_gene_list
        if self.crossover_method == "uniform":
            return [
                gene_list1[i] if random.random() < 0.5 else gene_list2[i]
                for i in range(min(len(gene_list1), len(gene_list2)))
            ]
        crossover = random.randint(0, len(gene_list1))
        new_gene_list = gene_list1[:crossover]
        new_gene_list.extend(gene_list2[crossover:])
        return new_gene_list

    def _tournament_select(self, tournament_size=3):
        """Select one organism via tournament selection.

        Picks tournament_size random contestants and returns the fittest.
        """
        contestants = random.sample(self.population, min(tournament_size, len(self.population)))
        if self.rev_pop_sort:
            return max(contestants, key=lambda o: o.points)
        return min(contestants, key=lambda o: o.points)

    def _compute_mutation_chance(self):
        """Return diversity-based adaptive mutation rate.

        Low diversity → higher mutation to escape local maxima.
        """
        diversity = len({org.points for org in self.population}) / len(self.population)
        if diversity < 0.1:
            return 0.8
        if diversity < 0.3:
            return 0.5
        return 0.2

    def breed_population(
        self,
        pool_percentage=50,
        type_pools=None,
        tournament_size=3,
        elite_percentage=5,
        immigration_rate=5,
        available_genes=None,
    ):
        """Evolve the population one generation.

        :param pool_percentage: Kept for API compatibility; selection is now tournament-based.
        :param type_pools: Optional {param_name: [compatible_inputs]} for type-aware mutation.
        :param tournament_size: Number of contestants per tournament selection round.
        :param elite_percentage: Percent of population preserved unchanged each generation.
        :param immigration_rate: Percent of population replaced with fresh random organisms.
        :param available_genes: Optional list of all valid values for genes[0] (param names);
            enables variable-length add/remove operators during mutation.
        """
        self.sort_population()
        best_score = self.population[0].points

        if self._best_score is None:
            self._best_score = best_score

        improved = (
            (best_score > self._best_score)
            if self.rev_pop_sort
            else (best_score < self._best_score)
        )
        if improved:
            self._best_score = best_score
            self._stagnation_counter = 0
        else:
            self._stagnation_counter += 1

        # Partial restart when stagnated: keep top 20%, regenerate the rest
        if self._stagnation_counter >= self.population_count * 2:
            keep_count = max(1, int(self.population_count * 0.2))
            survivors = self.population[:keep_count]
            fresh = []
            while len(fresh) < self.population_count - keep_count:
                org = Organism(genes=self.gene_base[:])
                org.generate_genes(gen_func=self.generator_function, count=self.gene_length)
                fresh.append(org)
            self.population = survivors + fresh
            self._stagnation_counter = 0
            return

        mutation_chance = self._compute_mutation_chance() if self.mutate else 0.0

        # Elites: deep-copied so later mutation doesn't corrupt them
        elite_count = max(2, int(self.population_count * elite_percentage / 100))
        elites = [
            Organism(genes=copy.deepcopy(org.genes), points=org.points)
            for org in self.population[:elite_count]
        ]

        immigration_count = max(1, int(self.population_count * immigration_rate / 100))

        next_generation = elites[:]

        # Fill via tournament selection + offspring mutation
        while len(next_generation) < self.population_count - immigration_count:
            parent1 = self._tournament_select(tournament_size)
            parent2 = self._tournament_select(tournament_size)
            new_org = Organism(genes=self._breed_pair(parent1.genes, parent2.genes))
            if self.mutate and random.random() <= mutation_chance:
                new_org.mutate(type_pools=type_pools, available_genes=available_genes)
            next_generation.append(new_org)

        # Immigrants: fully random organisms injected each generation
        while len(next_generation) < self.population_count:
            org = Organism(genes=self.gene_base[:])
            org.generate_genes(gen_func=self.generator_function, count=self.gene_length)
            next_generation.append(org)

        self.population = next_generation

    def sort_population(self, reverse=None):
        """Sort the population by the number of points they have."""
        reverse = reverse or self.rev_pop_sort
        self.population = sorted(self.population, key=lambda org: org.points, reverse=reverse)


@attr.s(slots=True)
class Organism:
    """The actor class that is the target of evolution."""

    genes = attr.ib(validator=attr.validators.instance_of(list), cmp=False)
    points = attr.ib(default=0)

    def generate_genes(self, gen_func=None, count=None):
        """Randomly sort the genes to provide different combinations."""
        if gen_func and count:
            if count == 1:
                self.genes = gen_func()
            else:
                self.genes = [gen_func() for _ in range(count)]
        if isinstance(self.genes[0], list):
            self.genes = self.genes[:]
            for i in range(len(self.genes)):
                self.genes[i] = self.genes[i][:]
                random.shuffle(self.genes[i])
        else:
            self.genes = self.genes[:]
            random.shuffle(self.genes)

    def mutate(self, gene_base=None, mutation_chance=0.1, type_pools=None, available_genes=None):
        """Randomly mutate genes.

        :param gene_base: Optional fallback pool for replacement mutation values.
        :param mutation_chance: Probability of swap vs. replacement per gene/sublist.
        :param type_pools: Optional {param_name: [compatible_inputs]} for type-aware replacement
            of the inputs sublist in 2-list gene structures.
        :param available_genes: Optional list of all valid param names; enables variable-length
            add/remove operators for 2-list gene structures.
        """
        if isinstance(self.genes[0], list):
            param_names = self.genes[0] if len(self.genes) >= 2 else []

            # Variable-length operators (2-list structures only): ~10% chance each
            if available_genes and len(self.genes) >= 2:
                if random.random() < 0.1:
                    # Add: pick a param not already present, with a type-compatible input
                    candidates = [g for g in available_genes if g not in self.genes[0]]
                    if candidates:
                        new_param = random.choice(candidates)
                        pool = (type_pools.get(new_param) or []) if type_pools else []
                        if not pool:
                            pool = self.genes[1] or []
                        if pool:
                            self.genes[0].append(new_param)
                            self.genes[1].append(random.choice(pool))
                            param_names = self.genes[0]

                if random.random() < 0.1 and len(self.genes[0]) > 1:
                    # Remove: drop a random pair; floor at length 1
                    idx = random.randint(0, len(self.genes[0]) - 1)
                    self.genes[0].pop(idx)
                    self.genes[1].pop(idx)
                    param_names = self.genes[0]

            for i in range(len(self.genes)):
                if not self.genes[i]:
                    continue
                if random.random() < mutation_chance:
                    g1 = random.choice(range(len(self.genes[i])))
                    g2 = random.choice(range(len(self.genes[i])))
                    self.genes[i][g1], self.genes[i][g2] = (
                        self.genes[i][g2],
                        self.genes[i][g1],
                    )
                else:
                    idx = random.randint(0, len(self.genes[i]) - 1)
                    if i == 1 and type_pools and param_names:
                        param = param_names[idx] if idx < len(param_names) else None
                        pool = type_pools.get(param, self.genes[i]) if param else self.genes[i]
                        self.genes[i][idx] = random.choice(pool) if pool else self.genes[i][idx]
                    else:
                        self.genes[i][idx] = random.choice(self.genes[i])
        elif random.random() < mutation_chance:
            gene1 = random.choice(range(len(self.genes)))
            gene2 = random.choice(range(len(self.genes)))
            self.genes[gene1], self.genes[gene2] = (self.genes[gene2], self.genes[gene1])
        else:
            genes = gene_base or self.genes
            self.genes[random.randint(0, len(self.genes) - 1)] = random.choice(genes[:])
