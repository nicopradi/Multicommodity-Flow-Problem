
                    # ------------- COLUMN GENERATION ALGORITHM FOR THE MEDIUM INSTANCE ------------- 

from __future__ import print_function

import sys
import time

import cplex
from cplex.exceptions import CplexSolverError

import numpy as np
np.set_printoptions(threshold=np.nan)

import openpyxl

from medium_data import getNodes, getArcs, getCommodities, getCosts # python script to get the data


def dijkstra(origin, cost, mostUsedNode, mostUsedArc):
    """ Return the shortest paths from origin
        If mostUsedNode/mostUsedArc is not empty, delete the corresponding nodes/arc from the graph,
        then compute the shortest paths from origin.
        
        origin : Station from which the method computes the shortest paths
        cost : Adjency matrix, each entry contains : [cost between the two nodes, corresponding arc_id]
        mostUsedNode : Nodes that will be ignored
        mostUsedArc : Arcs that will be ignored
    """
#   -------- DIJKSTRA'S ALGORITHM --------

    # -- Delete nodes/arcs if any given -- 
    if(len(mostUsedNode) != 0): 
        mostUsedNode = list(mostUsedNode) # Convert to list to iterate
        for j in range(len(mostUsedNode)):
            for i in range(nStations):
                cost[i, mostUsedNode[j], 0] = 0 # Disconnect the mostUsedNode from all others

    if(len(mostUsedArc) != 0):
        mostUsedArc = list(mostUsedArc) # Convert to list to iterate
        for j in range(len(mostUsedArc)):
            cost[ arc[mostUsedArc[j]][0]-1 , arc[mostUsedArc[j]][1]-1 , 0] = 0 # Disconnect the mostUsedArc from all others  
                
    labels = np.full((nStations), np.inf) # Contains the cost of the shortest paths from origin with initial value = infinite
    labels[origin] = 0
    
    precedent_nodes = np.full((nStations), -1, dtype=int) # Contains the previous node of each node in the shortest paths
    precedent_arcs = np.full((nStations), -1, dtype=int) # Contains the previous arc of each node in the shortest paths
    
    toTreat = np.array([origin]) # Nodes that need to be processed

    while True:
        currentNode = toTreat[np.argmin(np.take(labels, toTreat))] # Pick the node with lowest shortest path distance from the set toTreat

        for i in np.nonzero(cost[currentNode, :, 0])[0]: # For all neighbors of currentNode
            if(labels[i] > labels[currentNode] + cost[currentNode, i, 0]): # If a better path if found
                    
                labels[i] = labels[currentNode] + cost[currentNode, i, 0] # Update the value
                precedent_nodes[i] = currentNode # Get the node_id
                precedent_arcs[i] = cost[currentNode, i, 1] # Get the arc_id
                toTreat = np.append(toTreat, i) # As we found a better path to go to i, need to treat all the neighbors of i

        toTreat = np.delete(toTreat,np.where(toTreat==currentNode)[0]) # Delete the node we just processed
        
        if(toTreat.size == 0): # If there is no node left to treat, we are sure we obtained the best solution.
            break

    return labels, precedent_nodes, precedent_arcs

def getInitSet():
    """ Return a feasible set of inital variables : Greedy algorithm
        1. Compute the shortest path for each commodity
        2. Sort the commodities by the outdegree value of their shortest path
        (outdegree of a path = sum of the outdegree of all nodes the path contains, except the destination node)
        3. Iterate over the sorted commodity, for each of them, try to route it through its shortest path
            3.1 If the nodes/arcs capacity constraints are not violated
                -> Route the commoditiy through its shortest path
                Otherwise
                -> Compute the shortest path for the commodity, ignoring the violated nodes/arcs
                    3.1.1 If there is no shortest path
                    -> Put the commodity at the beginning of the list
                          Otherwise
                          -> Return to 3.1
        4. If all commodities have a feasible path, Algorithm returns
           Otherwise : Return to step 3
    """

    #   -------- GET INITIAL SET OF PROMISSING VARIABLES --------

    shortest_paths_original = np.zeros((nStations, nStations), dtype=int) # Represent the shortest path distance between each nodes in the original network
    previous_nodes_original = np.zeros((nStations, nStations), dtype=int) # Represent the previous node of each node of the shortest path from index
    previous_arcs_original = np.zeros((nStations, nStations), dtype=int) # Represent the previous arc of each node of the shortest path from index

    distance_done = set() # Nodes for which dijkstra's algorithm has already been run
    sorting = 0 # Number of iteration over all commodities
    
    outdegree = np.zeros(nCommodities) # Contain the outdegree of the shortest path of each commodity
    sortedCommo = range(nCommodities) # Contains the indices by which we are going to iterate over the commodities
    
    while(sorting < 5): # If we haven't iterate too much over the commodities (otherwise : consider the problem unfeasible)

        current_capacities_nodes = [capacity_node[index] for index in [row[2]-1 for row in node]] # To verify the capacities of the nodes are not violated
        current_capacities_arcs = [row[3] for row in arc] # To verify the capacities of the arcs are not violated

        pathsK_nodes = [[] for i in range(nCommodities)] # ReInitialize pathsK_nodes
        pathsK = [[] for i in range(nCommodities)] # ReInitialize pathsK

        unfeasible = False # Equals True if we found a unfeasible commodity
        count = 0
        
        for i in sortedCommo:
            count += 1
            print('COMMODITY N°', i+1, ' ---  ITERATION N°', count)
            
            not_add = 0 # Boolean variable, to know if we can take the original shortest path value
            current_cost = np.copy(cost) # ReInitialize the cost matrix
            
            to_Ignore_node = set() # Contains the nodes violated for the current commodity
            to_Ignore_arc = set() # Contains the arcs violated for the current commodity

            while True :
                start = commodities[i][0]
                dest = commodities[i][1]
                
                if(sorting == 0): # 1st iteration -> Compute the shortest path
                    if(start not in distance_done):

                        shortest_paths_original[start], previous_nodes_original[start], previous_arcs_original[start] = dijkstra(start, current_cost, to_Ignore_node, to_Ignore_arc)
                        distance_done.add(start)
                        
                    #Set the current shortest path values   
                    shortest_paths, previous_nodes, previous_arcs = shortest_paths_original[start], previous_nodes_original[start], previous_arcs_original[start]

                elif(not_add == 1): # A node/arc has to be ignored, re-run dijkstra's algorithm
                    shortest_paths, previous_nodes, previous_arcs = dijkstra(start, current_cost, to_Ignore_node, to_Ignore_arc)

                else: # If no nodes/arcs have to be ignored, take the original shortest path value
                    shortest_paths, previous_nodes, previous_arcs = shortest_paths_original[start], previous_nodes_original[start], previous_arcs_original[start]
    
                if(previous_nodes[dest] != -1): # Check the feasibilty of the commodity

                    to_Ignore_node = set() # Reset it for the ncurrent iteration
                    to_Ignore_arc = set()

                    # -- Generate the new path --
                    newPath_nodes = [0] * nStations # New path based on node_id
                    newPath_arcs = [0] * nArcs # New path based on arc_id
                
                    # By going backward from destination
                    while(dest != start):
                        
                        if(sorting > 0): # (The 1st iteration doesn't try to assign a commodity to its shortest path)
                            
                            if(current_capacities_nodes[dest] - commodities[i][2] < 0): # If a node is violated
                                print('block at node : ', dest)
                                to_Ignore_node.add(dest)
                                
                            if(current_capacities_arcs[previous_arcs[dest]] - commodities[i][2] < 0): # If an arc is violated
                                print('block at arc : ', previous_arcs[dest])
                                to_Ignore_arc.add(previous_arcs[dest])
                                
                        if(sorting == 0): # During the 1st iteration, compute the outdegree of the current path
                            outdegree[i] += node[ previous_nodes[dest] ][3]
                            
                        newPath_nodes[dest] = 1 * commodities[i][2] # Update the pathway value
                        newPath_arcs[previous_arcs[dest]] = 1 * commodities[i][2]
                        
                        dest = previous_nodes[dest] # Go backward
    
                    if(len(to_Ignore_node) == 0 and len(to_Ignore_arc) == 0): # We found a feasible path for the current commodity
                        
                        current_capacities_nodes = np.subtract(current_capacities_nodes, np.asarray(newPath_nodes))
                        current_capacities_arcs = np.subtract(current_capacities_arcs, np.asarray(newPath_arcs))
                        break # Go to the next commodity
                
                    else: # We violated a capacity constraint, recompute shortest path without them
                        if(not_add == 0):
                            not_add = 1 # Do not take the original shortest path anymore

                else: # There is no feasible path between the origin and destination
                    
                    unfeasible = True
                    sortedCommo = np.delete(sortedCommo, np.argwhere(sortedCommo == i)) # Delete the unfeasible commodity
                    sortedCommo = np.insert(sortedCommo, 0, i) # And put it at the begining of the list 
                    print('UNFEASIBLE')
                    print()
                    break
    
            newPath_nodes.append( shortest_paths[commodities[i][1]] ) # Append the cost of the path found
            pathsK_nodes[i].append(newPath_nodes)
            
            pathsK[i].append(newPath_arcs)
                
        if(sorting == 0): #Sort the commodities indices by their shortest path outdegree
            sortedCommo = np.argsort(outdegree)
            
        sorting += 1
        
        if(unfeasible == False and sorting > 1):
            return pathsK_nodes, pathsK
    
def dual_of_Restrited(pathsK_nodes, pathsK):
    """ Return the dual variables of the restricted master problem

        pathsK_nodes : Contains the considered paths(node-based) for each commodity
        pathsK : Contains the considered paths(arc-based) for each commodity
    """
#   ------------- DUAL OF THE RESTRICTED MASTER PROBLEM -------------
    
    model = cplex.Cplex() # Initialize the model
    model.objective.set_sense(model.objective.sense.maximize) # Set the objective function to maximization

    # -- Add variables --
    # Correspond to the flow conservation constraints
    for i in range(nCommodities):
        model.variables.add(obj = [1], lb = [-cplex.infinity], ub = [cplex.infinity],#obj contains the coefficients of the decision variables in the objective function
                            types = [model.variables.type.continuous],
                            names = ['Y( K_' + str(i) + ')'])
        
    # Correspond to the node capacity constraints 
    for i in range(nStations):
        model.variables.add(obj = [ capacity_node[node[i][2]-1] ], lb = [-cplex.infinity], ub = [0],
                            types = [model.variables.type.continuous],
                            names = ['Y( ' + str(node[i][0])  + ')'])
        
    # Correspond to the arc capacity constraints 
    for i in range(nArcs):
        model.variables.add(obj = [ arc[i][3] ], lb = [-cplex.infinity], ub = [0],
                            types = [model.variables.type.continuous],
                            names = ['Y( ' + str(arc[i][0]-1) +','+ str(arc[i][1]-1) + ')'])
        
    # -- Add constraints -- 
    for i in range(nCommodities):
        for j in range(len(pathsK_nodes[i])):
            ind = []# Put the indices of the non-zero variables of the current constraint
            val = []# Put their coefficients here
            row = []
            ind.append(i)
            val.append(1)
            for k in range(nStations):
                if(pathsK_nodes[i][j][k] > 0): # Check which node is contained in the current paths (do not include starting node)
                    ind.append(nCommodities+k)
                    val.append(commodities[i][2])
            for l in range(nArcs):
                if(pathsK[i][j][l] > 0): # Check which arc is contained in the current paths
                    ind.append(nCommodities+nStations+l)
                    val.append(commodities[i][2])
            row.append([ind, val])
            model.linear_constraints.add(lin_expr = row,
                                     senses = "L", #Less or equal than constraint
                                     rhs = [ pathsK_nodes[i][j][nStations]*float(commodities[i][2]) ] ) # Right Hand Side of the constraint

    try:
        print("\n\n----------- RESTRICTED DUAL SOLUTION : -----------\n")
        model.set_results_stream(None)
        model.set_warning_stream(None)
        model.solve()
        model.write('test_dual.lp')
        
    except CplexSolverError as e:
        print("Exception raised during dual of restricted problem: " + e)

    # Return the dual variables corresponding to the commodities, arcs and nodes constraints
    return model.solution.get_values()[:nCommodities] , model.solution.get_values()[nCommodities:nCommodities+nStations], model.solution.get_values()[nCommodities+nStations:]

def restricted_Master(pathsK_nodes, pathsK):
    """ Return the solution to the restricted master problem, as well as, the dual variables

        pathsK_nodes : Contains the considered paths(node-based) for each commodity
        pathsK : Contains the considered paths(arc-based) for each commodity
    """
    
#   ------------- SOLVE THE RESTRICTED MASTER PROBLEM -------------
        
    model = cplex.Cplex() # Initialize the model
    model.objective.set_sense(model.objective.sense.minimize) ## Set the objective function to minimization
    
    # -- Add variables
    for i in range(nCommodities):
        for j in range(len(pathsK_nodes[i])):
            model.variables.add(obj = [pathsK_nodes[i][j][nStations]*float(commodities[i][2])], lb = [0], ub = [1],#obj contains the coefficients of the decision variables in the objective function                               
                                types = [model.variables.type.continuous],
                                names = ['P(' + str(i) + ',' + str(j) + ')']) 

    # -- Add constraints -- 
    #Flow conservation constraints :
    count = 0 # To iterate over the indices of the decision variables
    for i in range(nCommodities):
        ind = [] # Put the indices of the non-zero variables of the current constraint
        val = [] # Put their coefficients here
        row = []
        for j in range(len(pathsK_nodes[i])):
            ind.append(count) 
            val.append(1)
            count += 1
        row.append([ind, val])
        model.linear_constraints.add(lin_expr = row,
                                     senses = "E", #Equality constraint
                                     rhs = [1] ) # Right Hand Side of the constraint
 
    #Node capacity constraints :
    for i in range(nStations): 
        ind, val, row = [], [], []
        count = 0
        for j in range(nCommodities): #For each commodity path, check each time a path contains the node (do not include starting node)
            for k in range(len(pathsK_nodes[j])):
                if(pathsK_nodes[j][k][i] > 0): # If it is the case, add the decision variable index to the constraint
                    ind.append(count)
                    val.append(commodities[j][2]) # With its coefficiant
                count += 1
        row.append([ind, val])
        model.linear_constraints.add(lin_expr = row,
                                     senses = "L", # Less-than
                                     rhs = [ capacity_node[node[i][2]-1] ] ) #Capacity of the node (-1 because type_id start at 1)

    #Arc capacity constraints :
    for i in range(nArcs): 
        ind, val, row = [], [], []
        count = 0
        for j in range(nCommodities): #For each commodity path, check each time a path contains the node (do not include starting node)
            for k in range(len(pathsK[j])):
                if(pathsK[j][k][i] > 0): # If it is the case, add the decision variable index to the constraint
                    ind.append(count)
                    val.append(commodities[j][2]) # With its coefficiant
                count += 1
        row.append([ind, val])
        model.linear_constraints.add(lin_expr = row,
                                     senses = "L", # Less-than
                                     rhs = [ arc[i][3] ] ) #Capacity of the node (-1 because type_id start at 1)
        
    try:
        print("\n\n----------- RESTRICTED MASTER SOLUTION : -----------\n")
        model.set_results_stream(None)
        model.set_warning_stream(None)
        model.solve()
        model.write('test_restricted.lp')
        print("\n")
        print("Solution primal : ",model.solution.get_values())
        
        #Print the solution
        count = 0
        for i in range(nCommodities):
            for j in range(len(pathsK_nodes[i])):
                
                indices = [k for k, x in enumerate(pathsK_nodes[i][j]) if (x > 0 and k < nStations)] #Get the indices of the nodes contained in the current path

                print("\t", model.solution.get_values(count)*commodities[i][2] ,"units of commodity n°", i+1 ,"on path", node[commodities[i][0]][0],''
                      + ' '.join([node[k][0] for k in indices]) + ". Length path : " + str(pathsK_nodes[i][j][nStations]) )
                count += 1
                
        print("\nTotal cost = " + str(model.solution.get_objective_value()))
        
        dualCommodities, dualStations, dualArcs = dual_of_Restrited(pathsK_nodes, pathsK) # Compute the dual variables and print them
        
        print()
        for i in range(len(dualCommodities)):
            if(dualCommodities[i] != 0):
                print("Dual values y_K" + str(i) + " = "+ str(dualCommodities[i]))
                
        for i in range(len(dualStations)):
            if(dualStations[i] != 0):
                print("Dual values y_Node" + str(i) + " = "+ str(dualStations[i]))
                
        for i in range(len(dualArcs)):
            if(dualArcs[i] != 0):
                print("Dual values y_Arc" + str(i) + " = "+ str(dualArcs[i]))
            
    except CplexSolverError as e:
        print("Exception raised during restricted master problem: ", e)

    return model.solution.get_objective_value(), model.solution.get_values(), dualCommodities, dualStations, dualArcs

def pricingProblem(dualCommodities, dualStations, dualArcs): 
    """ Return the paths corresponding to the most negative reduced cost of each commodity

        1. For each commodity, solve the pricing problem using Dijkstra's algorithm
            1.1. If a path with a negative reduced cost is found, add it to the solution set
        2. Return the solution set, and the corresponding commodities
    """
#   ------------- SOLVE THE PRICING PROBLEM-------------

    reducedCost = 0 # Contains a negative value if we found a path with negative reduced cost
    
    forCommodity = [] # id of the commodity which will receive the new paths, if any
    bestPath_nodes = [] # Contains the paths which will be added (node_id's and cost)
    bestPath_arcs = [] # Contains the paths which will be added (arc_id's)

    shortest_from_node = np.full((nStations, nStations), np.inf) # Total cost of the shortest path from index
    previous_nodes = np.full((nStations, nStations), -1, dtype=int) # Nodes id to go backward
    previous_arcs = np.full((nStations, nStations), -1, dtype=int) # Arc id to go backward

    # -- Compute the new cost vector -- 
    cost_for_commo = getCosts(nStations)
    for i in range(nStations):
        for j in np.nonzero(cost_for_commo[i,:,0])[0]:
                cost_for_commo[i,j,0] = cost_for_commo[i,j,0] - dualStations[j]
                
    for i in np.nonzero(dualArcs)[0]:
        if(cost_for_commo[ arc[i][0]-1, arc[i][1]-1, 0 ] > 0): 
            cost_for_commo[ arc[i][0]-1, arc[i][1]-1, 0 ] = cost_for_commo[ arc[i][0]-1, arc[i][1]-1, 0 ] - dualArcs[i]
            
    # -- Run Dijkstra's -- 
    for i in range(nCommodities): #Solve the shortest path problem (with updated cost) for each commodity
        
        origin = commodities[i][0]
        dest = commodities[i][1]
        
        if( np.array_equal(previous_nodes[origin], np.full((nStations), -1, dtype=int)) ): # Haven't run Dijkstra yet for this origin
            shortest_from_node[origin], previous_nodes[origin], previous_arcs[origin] = dijkstra(origin, cost_for_commo, set(), set())
                          
        currentReducedCost = (shortest_from_node[origin, dest] * commodities[i][2]) - dualCommodities[i] #Compute the reducedCost
        
        if(currentReducedCost < 0):
            
            # -- Construct the new path --
            newPath_nodes = [0] * (nStations+1)
            newPath_arcs = [0] * nArcs
            
            # By going backward from destination
            while(dest != origin):
                newPath_nodes[dest] = 1 * commodities[i][2]
                newPath_nodes[nStations] += arc[previous_arcs[origin, dest]][2] # Compute the cost on the fly
                
                newPath_arcs[previous_arcs[origin, dest]] = 1 * commodities[i][2]

                dest = previous_nodes[origin, dest]

            reducedCost = round(currentReducedCost) # Round to avoid computational mistake (10^-23 instead of 0)
            forCommodity.append(i) 
            bestPath_nodes.append(newPath_nodes)
            bestPath_arcs.append(newPath_arcs)
        
        print("\n\n----------- PRICING PROBLEM SOLUTION FOR COMMODITY n°", i+1 ,": -----------\n")
        #Print reduced cost for the current commodity
        print()
        print("\n\tREDUCED COST : ", currentReducedCost)
        
    return reducedCost, bestPath_nodes, forCommodity, bestPath_arcs
                   
# ------------- DATA ------------- 

s_time_loading_data = time.time() # Time - 0 Start loading data

nStations, node = getNodes() # Get the nodes
nArcs, arc = getArcs() # Get the arcs
nCommodities, commodities = getCommodities() # Get the commodities
cost = getCosts(nStations) # Get the cost adjency matrix

scale_capacity = 1/75 # Variable used to scale up or down the capacity of the arcs
arc = [[row[0], row[1], row[2], row[3]*scale_capacity] for row in arc] # Update arc capacities

capacity_node = [1000, 45, 45, 80] # Define a capacity value for each type of node

t_time_loading_data = time.time() # Time - 1 Start searching for feasible solution

# ------------- ALGORITHM -------------

#pathsK_nodes[k,i,j] with k = commodity_id // i = path_id of commodity k // j = node_id of the path 
pathsK_nodes = [[] for i in range(nCommodities)] # Contains all initial paths for each commodity (by nodes)

#pathsK[k,i,j] with k = commodity_id // i = path_id of commodity k // j = arc_id of the path 
pathsK = [[] for i in range(nCommodities)] # Contains all initial paths for each commodity (by arcs)

pathsK_nodes, pathsK = getInitSet() # Get the initial set of variable through Dijkstra and "route through best possible shortest path" method

t_time_init_set = time.time() # Time - 2 Start optimizing the problem

while True:
    
    obj_Function, solution, dualCommodities, dualStations, dualArcs = restricted_Master(pathsK_nodes, pathsK) #Solve the restricted master problem
    reducedCost, newPath, forCommodity, newPath_arc = pricingProblem(dualCommodities, dualStations, dualArcs) #Solve the pricing problem
    
    if(round(reducedCost) == 0): # round to avoid minor computational error (10^-23 for 0)
        
        t_time_solving = time.time() # Time - 3 Algorithm terminates
        
        #Print final solution
        count = 0
        for i in range(nCommodities):
            print()
            for j in range(len(pathsK_nodes[i])):
                
                indices = [k for k, x in enumerate(pathsK_nodes[i][j]) if (x > 0 and k < nStations) ] #Get the indices of the arcs contained in the current path

                print("\t", solution[count]*commodities[i][2] ,"units of commodity n°", i+1 ,"on path", node[commodities[i][0]][0],''
                      + ' '.join([node[k][0] for k in indices]) + ". Length path : " + str(pathsK_nodes[i][j][nStations]) )
                count += 1
                
        print("\nTotal cost = " + str(obj_Function))
        print("\nLoading data duration : ", t_time_loading_data - s_time_loading_data)
        print("Finding initial set duration : ", t_time_init_set - t_time_loading_data)
        print("Solving problem duration : ", t_time_solving - t_time_init_set)
        print("\nTotal duration : ", t_time_solving - s_time_loading_data)
        break
    
    else: # Add the new paths to the restricted set
        
        for j in range(len(newPath)):
            pathsK_nodes[forCommodity[j]].append(newPath[j])
            pathsK[forCommodity[j]].append(newPath_arc[j])
            
