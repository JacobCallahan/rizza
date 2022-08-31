# -*- encoding: utf-8 -*-
"""Genetic algorithm base classes."""
import random
from collections import deque
import attr

@attr.s()
class Population(object):
    """This class is the controller for the population of Orgamisms."""

    gene_base = attr.ib(
        validator=attr.validators.instance_of(list), cmp=False, repr=False)
    population_count = attr.ib(default=20)
    population = attr.ib(default=attr.Factory(list), cmp=False)
    top_scores = attr.ib(default=deque(maxlen=200), repr=False)
    rev_pop_sort = attr.ib(default=False, cmp=False, repr=False)
    generator_function = attr.ib(default=False, cmp=False, repr=False)
    gene_length = attr.ib(default=False, cmp=False, repr=False)
    mutate = attr.ib(default=True, cmp=False, repr=False)

    def __attrs_post_init__(self):
        """Generate a population of organisms."""
        self.population = []
        for _ in range(self.population_count):
            org = Organism(genes=self.gene_base[:])
            org.generate_genes(
                gen_func=self.generator_function, count=self.gene_length)
            self.population.append(org)

    def _breed_pair(self, gene_list1, gene_list2):
        """Breed two gene lists together.

        The first has a greater chance of passing their genes on.
        Random mutation is then given a chance to change the child.

        """
        # TODO now with nested lists and dict this requires rework
        new_gene_list = []
        if gene_list1 and gene_list2:
            # If we have nested genes, then recursively breed them
            if isinstance(gene_list1[0], list):
                for list1, list2 in zip(gene_list1, gene_list2):
                    new_gene_list.append(self._breed_pair(list1, list2))
            else:
                crossover = random.randint(0, len(gene_list1))
                new_gene_list = gene_list1[:crossover]
                new_gene_list.extend(gene_list2[crossover:])
        else:
            new_gene_list = gene_list1
        return new_gene_list

    def breed_population(self, pool_percentage=50):
        """"Cross breed the population with only the top percentage.

        :param pool_percentage: Percentage defines primary breeder cutoff.

        """
        # Create the breeding order. Those on top get more iterations.
        self.sort_population()
        breeders = self.population[
            :int(self.population_count * (float(pool_percentage) / 100))
        ]
        self.top_scores.append(breeders[0].points)
        # Add in some random members of the population
        while self.population_count > len(breeders):
            breeders.append(random.choice(self.population))

        next_generation = [Organism(genes=breeders[0].genes[:])]  # keep our best
        # Randomly mutate our existing population
        if self.mutate:
            if len(self.top_scores) == 200 and self.top_scores[0] == self.top_scores[-1]:
                mutation_chance = 0.9
            else:
                mutation_chance = 0.3
            for org in breeders:
                if random.random() <= mutation_chance:
                    org.mutate()

        while len(next_generation) < self.population_count:
            org1 = random.choice(breeders)
            org2 = random.choice(breeders)
            if org1 != org2:
                    new_org = Organism(genes=self._breed_pair(org1.genes, org2.genes))
            else:  # Avoid potential stagnation by introducing a new organism
                new_org = Organism(genes=self.gene_base[:])
                new_org.generate_genes(
                    gen_func=self.generator_function, count=self.gene_length)
            next_generation.append(new_org)
        self.population = next_generation

    def sort_population(self, reverse=None):
        """Sort the population by the number of points they have."""
        reverse = reverse or self.rev_pop_sort
        self.population = sorted(
            self.population, key=lambda org: org.points, reverse=reverse)

@attr.s(slots=True)
class Organism(object):
    """The is the actor class that is the target of evolution."""

    genes = attr.ib(validator=attr.validators.instance_of(list), cmp=False)
    points = attr.ib(default=0)

    def generate_genes(self, gen_func=None, count=None):
        """Randomly sort the genes to provide different combinations,
        keep the order between field and field inputs and arg and arg inputs """
        if gen_func and count:
            if count == 1:
                self.genes = gen_func()
            else:
                self.genes = [gen_func() for _ in range(count)]
        if isinstance(self.genes[0], list):
            self.genes = self.genes[:]
            for i in range(0, len(self.genes), 2):
                assert len(self.genes[i][:]) == len(self.genes[i+1][:])
                tmp = list(zip(self.genes[i][:], self.genes[i + 1][:]))
                # if tmp is empty there is nothing to unpack, therefore no need for shuffle
                if len(tmp) != 0:
                    random.shuffle(tmp)
                    self.genes[i][:], self.genes[i + 1][:] = zip(*tmp)
        else:
            self.genes = self.genes[:]
            random.shuffle(self.genes)

    def mutate(self, gene_base=None, mutation_chance=0.1):
        """Randomly mutate the list by swapping two genes around."""
        if isinstance(self.genes[0], list):
            for i in range(len(self.genes)):
                if random.random() < mutation_chance:
                        gene1 = random.choice(range(len(self.genes[i])))
                        gene2 = random.choice(range(len(self.genes[i])))
                        self.genes[i][gene1], self.genes[i][gene2] = (
                            self.genes[i][gene2], self.genes[i][gene1])
                else:  # Or we'll mutate to have a new/duplicate value introduced
                    self.genes[i][
                        random.randint(0, len(self.genes[i]) - 1)
                    ] = random.choice(self.genes[i])
        else:
            if random.random() < mutation_chance:
                    gene1 = random.choice(range(len(self.genes)))
                    gene2 = random.choice(range(len(self.genes)))
                    self.genes[gene1], self.genes[gene2] = (
                        self.genes[gene2], self.genes[gene1])
            else:  # Or we'll mutate to have a new/duplicate value introduced
                genes = gene_base or self.genes
                self.genes[
                    random.randint(0, len(self.genes) - 1)
                ] = random.choice(genes[:])
