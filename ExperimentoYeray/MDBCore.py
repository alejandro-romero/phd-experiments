from Simulador import *
from Episode import *
from CandidateStateEvaluator import *
from TracesBuffer import *
from CorrelationsManager import *
import logging
import pickle


class MDBCore(object):
    def __init__(self):

        # Object initialization
        self.simulator = Sim()
        self.tracesBuffer = TracesBuffer()
        self.tracesBuffer.setMaxSize(50)  # 15
        self.intrinsicMemory = EpisodicBuffer()
        self.intrinsicMemory.setMaxSize(100)

        self.episode = Episode()
        self.correlationsManager = CorrelationsManager()
        self.CSE = CandidateStateEvaluator()

        self.stop = 0
        self.iterations = 0
        self.it_reward = 0  # Number of iterarations before obtaining reward
        self.it_blind = 0  # Number of iterations the Intrinsic blind motivation is active
        self.n_execution = 1  # Number of the execution of the experiment

        self.activeMot = 'Int'  # Variable to control the active motivation: Intrinsic ('Int') or Extrinsic ('Ext')

        self.activeCorr = 0  # Variable to control the active correlation. It contains its index
        self.corr_sensor = 0  # 1 - Sensor 1, 2 - Sensor 2, ... n- sensor n, 0 - no hay correlacion
        self.corr_type = ''  # 'pos' - Positive correlation, 'neg' - Negative correlation, '' - no correlation

        self.iter_min = 0  # Minimum number of iterations to consider possible an antitrace

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG, filename='LogFile.log')
        logging.info('Iteration  ActiveMotivation  ActiveCorrelation  CorrelatedSensor  CorrelationType  Episode')

        self.noMotivManager = 0

        # Graph matrixes
        self.graph1 = []
        self.graph3 = []
        self.graph4 = []
        self.graph5 = []

        self.probUseGuided = 0  # Probability of using Intrinsic guided motivation during the Extrinsic use

    def run(self):

        # Import seed
        f = open('seed.pckl', 'rb')  # f = open('seed_robobo2.pckl', 'rb')
        seed = pickle.load(f)
        f.close()
        np.random.set_state(seed)

        # Save seed
        # seed = np.random.get_state()
        # f = open('seed.pckl', 'wb')
        # pickle.dump(seed, f)
        # f.close()

        self.main()
        self.plotGraphs()
        # Save/close logs

    def main(self):

        self.stop = 0
        self.iterations = 0

        # action = self.loadData()

        while not self.stop:
            if self.iterations == 0:
                action = 10
            # Sensorization in t (distances, action and motivation)
            self.episode.setSensorialStateT(self.simulator.get_sensorization())
            self.episode.setAction(action)
            # self.episode.setMotivation(self.activeMot)
            self.simulator.baxter_larm_action(action)
            # Sensorization in t+1 (distances and reward)
            self.episode.setSensorialStateT1(self.simulator.get_sensorization())
            #####POSIBLE CAMBIO
            self.episode.setReward(self.simulator.get_reward())
            #####
            # Save episode in the pertinent memories
            self.tracesBuffer.addEpisode(self.episode.getEpisode())
            self.intrinsicMemory.addEpisode(self.episode.getSensorialStateT1())
            ###########################
            if self.iterations > 0:
                self.writeLogs()
                self.debugPrint()
                self.saveGraphs()
            ###########################
            # Miro en el goal manager si hay reward y luego en la gestion de memoria elijo en
            # donde se deben guardar los datos corespondientes a eso

            # Check if a new correlation is needed
            self.correlationsManager.newCorrelation()
            if self.correlationsManager.correlations[self.activeCorr].i_reward_assigned == 0:
                self.correlationsManager.assignRewardAssigner(self.activeCorr, self.episode.getSensorialStateT1())
            # Memory Manager (Traces, weak traces and antitraces)
            if self.activeMot == 'Int':
                self.it_blind += 1
                self.noMotivManager = 0
                # If there is a reward, realise reward assignment and save trace in Traces Memory
                if self.episode.getReward():
                    ###
                    if self.correlationsManager.correlations[self.activeCorr].i_reward_assigned == 0:
                        self.correlationsManager.assignRewardAssigner(self.activeCorr,
                                                                      self.episode.getSensorialStateT1(), 1)
                    ###
                    self.simulator.restart_scenario()  # Restart scenario
                    self.correlationsManager.correlations[self.activeCorr].correlationEvaluator(
                        self.tracesBuffer.getTrace())  # Ya guardo aqui la traza debil
                    # self.activeCorr = len(self.correlationsManager.correlations) - 1

                    # self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(self.episode.getSensorialStateT1())
                    self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(
                        self.simulator.get_sensorization())  # Prueba provisional, despues debo seguir pasandole el sensorialStateT1, por lo que lo debo actuallizar al reiniciar el escenario
                    self.reinitializeMemories()
                    logging.info('Goal reward when Intrinsic Motivation')
                    # logging.info('State used to calculate the new active motivation: %s',
                    #             self.episode.getSensorialStateT1())
                    # logging.info('Real state: %s', self.simulator.get_sensorization())

                    self.it_reward = 0
                    self.it_blind = 0
                    self.n_execution += 1
                elif self.correlationsManager.getReward(self.activeCorr, self.simulator.get_reward(),
                                                        tuple(self.episode.getSensorialStateT1())):
                    self.correlationsManager.correlations[self.activeCorr].correlationEvaluator(
                        self.tracesBuffer.getTrace())
                    # The active correlation is now the correlation that has provided the reward
                    self.activeCorr = self.correlationsManager.correlations[self.activeCorr].i_reward
                    self.reinitializeMemories()
                    logging.info('Correlation reward when Intrinsic Motivation')

            elif self.activeMot == 'Ext':
                ##########
                if self.CSE.intrinsicGuidedActive:
                    self.noMotivManager = 1
                    # Miro la certeza y en el momento en que deje de ser mayor que el umbral,
                    # activo la motivacion extrinseca con la correlacion que habia activa antes
                    corr_sensor_comp, corr_type_comp = self.correlationsManager.correlations[self.activeCorr].getActiveCorrelation(tuple(self.episode.getSensorialStateT1()))
                    if corr_sensor_comp != self.corr_sensor or corr_type_comp != self.corr_type:
                        # Sigo la correlacion que estaba activa antes
                        self.CSE.followOriginalCorrelation = 1
                    if self.episode.getReward():  # GOAL MANAGER - Encargado de asignar la recompensa?
                        self.simulator.restart_scenario()  # Restart scenario
                        # Save as trace in TracesMemory of the correlated sensor
                        self.correlationsManager.correlations[self.activeCorr].addTrace(self.tracesBuffer.getTrace(),
                                                                                        self.corr_sensor, self.corr_type, 1)
                        self.CSE.intrinsicGuidedActive = 0
                        self.CSE.followOriginalCorrelation = 0
                        # self.activeCorr = len(self.correlationsManager.correlations) - 1
                        # self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(self.episode.getSensorialStateT1())
                        self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(
                            self.simulator.get_sensorization())  # Prueba provisional, despues debo seguir pasandole el sensorialStateT1, por lo que lo debo actuallizar al reiniciar el escenario
                        # Quizas poido restar scenario e ao salir de esto da motivacion activa, antes do motiv manager, comprobar cal e a activeCorrelation, mirar se eso me interfire con algo do que faigo antes
                        self.reinitializeMemories()
                        logging.info('Goal reward when Extrinsic Motivation')
                        # logging.info('State used to calculate the new active motivation: %s',
                        #              self.episode.getSensorialStateT1())
                        # logging.info('Real state: %s', self.simulator.get_sensorization())
                        self.noMotivManager = 0
                        # self.activeMot = 'Int'
                        self.it_reward = 0
                        self.it_blind = 0
                        self.n_execution += 1

                    elif self.correlationsManager.getReward(self.activeCorr, self.simulator.get_reward(),
                                                            tuple(self.episode.getSensorialStateT1())):
                        # Save as trace in TracesMemory of the correlated sensor
                        self.correlationsManager.correlations[self.activeCorr].addTrace(self.tracesBuffer.getTrace(),
                                                                                        self.corr_sensor, self.corr_type, 1)
                        self.CSE.intrinsicGuidedActive = 0
                        self.CSE.followOriginalCorrelation = 0
                        # The active correlation is now the correlation that has provided the reward
                        self.activeCorr = self.correlationsManager.correlations[self.activeCorr].i_reward
                        self.reinitializeMemories()
                        logging.info('Correlation reward when Extrinsic Motivation')

                        self.noMotivManager = 0
                    else:
                        # Check if the the active correlation is still active
                        if self.iter_min > 2:
                            if self.CSE.followOriginalCorrelation:
                                sens_t = self.tracesBuffer.getTrace()[-2][self.corr_sensor - 1]
                                sens_t1 = self.tracesBuffer.getTrace()[-1][self.corr_sensor - 1]
                            else:
                                sens_t = self.tracesBuffer.getTrace()[-2][self.CSE.corr_sensor_new - 1]
                                sens_t1 = self.tracesBuffer.getTrace()[-1][self.CSE.corr_sensor_new - 1]
                            dif = sens_t1 - sens_t
                            if (self.corr_type == 'pos' and dif <= 0) or (self.corr_type == 'neg' and dif >= 0):
                                # Guardo antitraza en el sensor correspondiente y vuelvo a comezar el bucle
                                self.correlationsManager.correlations[self.activeCorr].addAntiTrace(
                                    self.tracesBuffer.getTrace(), self.corr_sensor, self.corr_type, 1)
                                self.CSE.intrinsicGuidedActive = 0
                                self.CSE.followOriginalCorrelation = 0
                                # self.activeCorr = len(self.correlationsManager.correlations) - 1
                                # self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(self.episode.getSensorialStateT1())
                                self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(
                                    self.simulator.get_sensorization())  # Prueba provisional, despues debo seguir pasandole el sensorialStateT1, por lo que lo debo actuallizar al reiniciar el escenario
                                # self.tracesBuffer.removeAll()  # Reinitialize traces buffer
                                # self.iter_min = 0
                                self.reinitializeMemories()
                                logging.info('Antitrace in sensor %s of type %s', self.corr_sensor, self.corr_type)
                                logging.info('Sens_t %s, sens_t1 %s, diff %s', sens_t, sens_t1, dif)
                                # logging.info('State used to calculate the new active motivation: %s',
                                #              self.episode.getSensorialStateT1())
                                # logging.info('Real state: %s', self.simulator.get_sensorization())
                                self.noMotivManager = 0

                else:
                    ##########
                    self.noMotivManager = 1
                    if self.episode.getReward():
                        self.simulator.restart_scenario()  # Restart scenario
                        # Save as trace in TracesMemory of the correlated sensor
                        self.correlationsManager.correlations[self.activeCorr].addTrace(self.tracesBuffer.getTrace(),
                                                                                        self.corr_sensor, self.corr_type)
                        # self.activeCorr = len(self.correlationsManager.correlations) - 1
                        # self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(self.episode.getSensorialStateT1())
                        self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(
                            self.simulator.get_sensorization())  # Prueba provisional, despues debo seguir pasandole el sensorialStateT1, por lo que lo debo actuallizar al reiniciar el escenario
                        # Quizas poido restar scenario e ao salir de esto da motivacion activa, antes do motiv manager, comprobar cal e a activeCorrelation, mirar se eso me interfire con algo do que faigo antes
                        self.reinitializeMemories()
                        logging.info('Goal reward when Extrinsic Motivation')
                        # logging.info('State used to calculate the new active motivation: %s',
                        #              self.episode.getSensorialStateT1())
                        # logging.info('Real state: %s', self.simulator.get_sensorization())
                        self.noMotivManager = 0
                        # self.activeMot = 'Int'
                        self.it_reward = 0
                        self.it_blind = 0
                        self.n_execution += 1

                    elif self.correlationsManager.getReward(self.activeCorr, self.simulator.get_reward(),
                                                            tuple(self.episode.getSensorialStateT1())):
                        # Save as trace in TracesMemory of the correlated sensor
                        self.correlationsManager.correlations[self.activeCorr].addTrace(self.tracesBuffer.getTrace(),
                                                                                        self.corr_sensor, self.corr_type)
                        # The active correlation is now the correlation that has provided the reward
                        self.activeCorr = self.correlationsManager.correlations[self.activeCorr].i_reward
                        self.reinitializeMemories()
                        logging.info('Correlation reward when Extrinsic Motivation')
                        self.noMotivManager = 0
                    else:
                        # Check if the the active correlation is still active
                        if self.iter_min > 5:
                            sens_t = self.tracesBuffer.getTrace()[-2][self.corr_sensor - 1]
                            sens_t1 = self.tracesBuffer.getTrace()[-1][self.corr_sensor - 1]
                            dif = sens_t1 - sens_t

                            if (self.corr_type == 'pos' and dif <= 0) or (self.corr_type == 'neg' and dif >= 0):
                                # Guardo antitraza en el sensor correspondiente y vuelvo a comezar el bucle
                                self.correlationsManager.correlations[self.activeCorr].addAntiTrace(
                                    self.tracesBuffer.getTrace(), self.corr_sensor, self.corr_type)
                                # self.activeCorr = len(self.correlationsManager.correlations) - 1

                                # self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(self.episode.getSensorialStateT1())
                                self.activeCorr = self.correlationsManager.getActiveCorrelationPrueba(
                                    self.simulator.get_sensorization())  # Prueba provisional, despues debo seguir pasandole el sensorialStateT1, por lo que lo debo actuallizar al reiniciar el escenario
                                # self.tracesBuffer.removeAll()  # Reinitialize traces buffer
                                # self.iter_min = 0
                                self.reinitializeMemories()
                                logging.info('Antitrace in sensor %s of type %s', self.corr_sensor, self.corr_type)
                                logging.info('Sens_t %s, sens_t1 %s, diff %s', sens_t, sens_t1, dif)
                                # logging.info('State used to calculate the new active motivation: %s',
                                #              self.episode.getSensorialStateT1())
                                # logging.info('Real state: %s', self.simulator.get_sensorization())
                                self.noMotivManager = 0

            # MOTIVATION MANAGER
            self.MotivationManager()

            # CANDIDATE STATE EVALUATOR and ACTION CHOOSER
            # Generate new action
            SimData = (
                self.simulator.baxter_larm_get_pos(), self.simulator.baxter_larm_get_angle(),
                self.simulator.ball_get_pos(),
                self.simulator.ball_position, self.simulator.box1_get_pos())
            # # action = self.CSE.getAction(self.activeMot, SimData, tuple(self.episode.getSensorialStateT1()),
            # #                             self.corr_sensor, self.corr_type, self.intrinsicMemory.getContents())
            # action = self.CSE.getAction(self.activeMot, SimData, tuple(self.simulator.get_sensorization()),
            #                             self.corr_sensor, self.corr_type,
            #                             self.intrinsicMemory.getContents())  # Prueba mientras no solucione lo del reward de scenario y actualizar el estado s(t+1)

            if self.corr_sensor == 1:
                if self.corr_type == 'pos':
                    Tb = self.correlationsManager.correlations[self.activeCorr].S1_pos.numberOfGoalsWithoutAntiTraces
                else:
                    Tb = self.correlationsManager.correlations[self.activeCorr].S1_neg.numberOfGoalsWithoutAntiTraces
            elif self.corr_sensor == 2:
                if self.corr_type == 'pos':
                    Tb = self.correlationsManager.correlations[self.activeCorr].S2_pos.numberOfGoalsWithoutAntiTraces
                else:
                    Tb = self.correlationsManager.correlations[self.activeCorr].S2_neg.numberOfGoalsWithoutAntiTraces
            else: # self.corr_sensor = 0 -> No hay correlacion
                Tb = 0

            maxTb = self.correlationsManager.correlations[self.activeCorr].Tb_max

            action = self.CSE.getAction(self.activeMot, SimData, tuple(self.simulator.get_sensorization()),
                                        self.corr_sensor, self.corr_type,
                                        self.intrinsicMemory.getContents(), Tb, maxTb,
                                        self.correlationsManager.correlations[self.activeCorr].established,
                                        self.probUseGuided)

            # Others
            # self.writeLogs()
            # self.debugPrint()
            self.iter_min += 1
            self.saveData()
            self.iterations += 1
            self.it_reward += 1
            self.stopCondition()
            self.episode.cleanEpisode()
            # plt.pause(0.0001)

    def stopCondition(self):

        if self.iterations > 8000:
            self.stop = 1

    def writeLogs(self):
        logging.debug('%s  -  %s  -  %s  -  %s  -  %s  -  %s', self.iterations, self.activeMot, self.activeCorr,
                      self.corr_sensor, self.corr_type, self.episode.getEpisode())

    def debugPrint(self):
        print '------------------'
        print "Iteration: ", self.iterations
        print "Active correlation: ", self.activeCorr
        print "Active motivation: ", self.activeMot
        print "Intrinsic guided motivation active: ", self.CSE.intrinsicGuidedActive
        print "Correlated sensor: ", self.corr_sensor, self.corr_type
        print "Trazas consecutivas S2 neg: ", self.correlationsManager.correlations[
            self.activeCorr].S2_neg.numberOfGoalsWithoutAntiTraces
        print "Trazas consecutivas S1 neg: ", self.correlationsManager.correlations[
            self.activeCorr].S1_neg.numberOfGoalsWithoutAntiTraces

    def reinitializeMemories(self):
        self.tracesBuffer.removeAll()  # Reinitialize traces buffer
        self.iter_min = 0
        self.intrinsicMemory.removeAll()  # Reinitialize intrinsic memory
        self.intrinsicMemory.addEpisode(self.episode.getSensorialStateT1())

    def MotivationManager(self):
        if not self.noMotivManager and not self.CSE.intrinsicGuidedActive:
            # self.corr_sensor, self.corr_type = self.correlationsManager.getActiveCorrelation(
            #     tuple(self.episode.getSensorialStateT1()), self.activeCorr)
            self.corr_sensor, self.corr_type = self.correlationsManager.getActiveCorrelation(
                tuple(self.simulator.get_sensorization()),
                self.activeCorr)  # Prueba, mientras no actualizo el tema del estado despues del reward de scenario
            if self.corr_sensor == 0:
                self.activeMot = 'Int'
            else:
                if self.activeMot == 'Int':
                    # self.tracesBuffer.removeAll()
                    self.iter_min = 0
                self.activeMot = 'Ext'
                self.probUseGuided = 0#np.random.choice([0, 1], p=[0.5, 0.5])

    def saveGraphs(self):
        # Graph 1 - Iterations to reach the goal vs. Total number of iterations
        self.graph1.append(
            (self.iterations, self.episode.getReward(), self.it_reward, self.it_blind,
             len(self.correlationsManager.correlations), self.activeMot, self.activeCorr,
             self.episode.getSensorialStateT1()))
        # Graph 2 - Iterations blind Intrinsic active vs. Total number of iterations
        # self.graph2.append((self.iterations, self.episode.getReward(), self.it_blind, len(self.correlationsManager.correlations)))
        # Graph 3 - Representative execution: Active motivation/correlation and sensor values
        # self.graph3.append((self.iterations, self.it_reward, self.activeMot, self.activeCorr, self.episode.getSensorialStateT1()))
        if self.n_execution == 1:
            self.graph3.append(
                (self.iterations, self.episode.getReward(), self.it_reward, self.it_blind,
                 len(self.correlationsManager.correlations), self.activeMot, self.activeCorr,
                 self.episode.getSensorialStateT1()))

        if self.n_execution == 20:
            self.graph4.append(
                (self.iterations, self.episode.getReward(), self.it_reward, self.it_blind,
                 len(self.correlationsManager.correlations), self.activeMot, self.activeCorr,
                 self.episode.getSensorialStateT1()))

        if self.n_execution == 40:
            self.graph5.append(
                (self.iterations, self.episode.getReward(), self.it_reward, self.it_blind,
                 len(self.correlationsManager.correlations), self.activeMot, self.activeCorr,
                 self.episode.getSensorialStateT1()))

    def plotGraphs(self):
        # Graph 1
        plt.figure()
        for i in range(len(self.graph1)):
            if self.graph1[i][1]:
                plt.plot(self.graph1[i][0], self.graph1[i][2], 'ro')
        for i in range(len(self.graph1)):
            if self.graph1[i][4] > self.graph1[i - 1][4]:
                plt.axvline(x=self.graph1[i][0])
        plt.axes().set_xlabel('Iterations')
        plt.axes().set_ylabel('Iterations needed to reach the goal')
        plt.grid()

        # Graph 2
        plt.figure()
        for i in range(len(self.graph1)):
            if self.graph1[i][1]:
                plt.plot(self.graph1[i][0], self.graph1[i][3], 'ro', color='green')
        for i in range(len(self.graph1)):
            if self.graph1[i][4] > self.graph1[i - 1][4]:
                plt.axvline(x=self.graph1[i][0])
        plt.axes().set_xlabel('Iterations')
        plt.axes().set_ylabel('Iterations the Ib motivation is active')
        plt.grid()

        # # Graph 3
        # plt.figure()
        # plt.title('Representative execution: n1')
        # sens1 = []
        # sens2 = []
        # active_corr = []
        # for i in range(len(self.graph3)):
        #     # Reorganize sensor values to plot them
        #     sens1.append(self.graph3[i][7][0])
        #     sens2.append(self.graph3[i][7][1])
        #     if self.graph3[i][5] == 'Int':
        #         active_corr.append(100)
        #     else:
        #         active_corr.append((self.graph3[-1][4] - self.graph3[i][6] + 1) * 100)
        # iterations = list(range(len(self.graph3)))
        # plt.plot(iterations, sens1, marker='.', color='cyan', linewidth=0.5)
        # plt.plot(iterations, sens2, marker='.', color='green', linewidth=0.5)
        # plt.plot(iterations, active_corr, marker='.', color='red', linewidth=2.0)
        # plt.axes().set_xlabel('Iterations')
        # plt.axes().set_ylabel('Legend')
        # plt.grid()
        # # for i in range(len(self.graph1)):
        # #     if self.graph1[i][1]:
        # #         plt.plot(self.graph1[i][0], self.graph1[i][3], 'ro')
        # # for i in range(len(self.graph1)):
        # #     if self.graph1[i][1]:  # Draw a line in each reward to show that a new execution is starting
        # #         plt.axvline(x=self.graph3[i][0], color='red')
        #
        # # Graph 4
        # plt.figure()
        # plt.title('Representative execution: n20')
        # sens1 = []
        # sens2 = []
        # active_corr = []
        # for i in range(len(self.graph4)):
        #     # Reorganize sensor values to plot them
        #     sens1.append(self.graph4[i][7][0])
        #     sens2.append(self.graph4[i][7][1])
        #     if self.graph4[i][5] == 'Int':
        #         active_corr.append(100)
        #     else:
        #         active_corr.append((self.graph4[-1][4] - self.graph4[i][6] + 1) * 100)
        # iterations = list(range(len(self.graph4)))
        # plt.plot(iterations, sens1, marker='.', color='cyan', linewidth=0.5)
        # plt.plot(iterations, sens2, marker='.', color='green', linewidth=0.5)
        # plt.plot(iterations, active_corr, marker='.', color='red', linewidth=2.0)
        # plt.axes().set_xlabel('Iterations')
        # plt.axes().set_ylabel('Legend')
        # plt.grid()
        #
        # # Graph 5
        # plt.figure()
        # plt.title('Representative execution: n40')
        # sens1 = []
        # sens2 = []
        # active_corr = []
        # for i in range(len(self.graph5)):
        #     # Reorganize sensor values to plot them
        #     sens1.append(self.graph5[i][7][0])
        #     sens2.append(self.graph5[i][7][1])
        #     if self.graph5[i][5] == 'Int':
        #         active_corr.append(100)
        #     else:
        #         active_corr.append((self.graph5[-1][4]-self.graph5[i][6] + 1)*100)
        # iterations = list(range(len(self.graph5)))
        # plt.plot(iterations, sens1, marker='.', color='cyan', linewidth=0.5)
        # plt.plot(iterations, sens2, marker='.', color='green', linewidth=0.5)
        # plt.plot(iterations, active_corr, marker='.', color='red', linewidth=2.0)
        # plt.axes().set_xlabel('Iterations')
        # plt.axes().set_ylabel('Legend')
        # plt.grid()


    def saveData(self):  # , action, seed):
        f = open('prueba.pckl', 'wb')
        pickle.dump(self.episode, f)
        pickle.dump(len(self.correlationsManager.correlations), f)
        for i in range(len(self.correlationsManager.correlations)):
            pickle.dump(self.correlationsManager.correlations[i].S1_pos, f)
            pickle.dump(self.correlationsManager.correlations[i].S1_neg, f)
            pickle.dump(self.correlationsManager.correlations[i].S2_pos, f)
            pickle.dump(self.correlationsManager.correlations[i].S2_neg, f)
            pickle.dump(self.correlationsManager.correlations[i].corr_active, f)
            pickle.dump(self.correlationsManager.correlations[i].corr_type, f)
            pickle.dump(self.correlationsManager.correlations[i].established, f)
            pickle.dump(self.correlationsManager.correlations[i].i_reward, f)
            pickle.dump(self.correlationsManager.correlations[i].i_reward_assigned, f)
        pickle.dump(self.activeMot, f)
        pickle.dump(self.activeCorr, f)
        pickle.dump(self.corr_sensor, f)
        pickle.dump(self.corr_type, f)
        pickle.dump(self.iterations, f)
        # pickle.dump(action, f)
        # pickle.dump(seed, f)
        f.close()

    def loadData(self):
        f = open('prueba.pckl', 'rb')
        self.episode = pickle.load(f)
        numero = pickle.load(f)
        for i in range(numero):
            self.correlationsManager.correlations.append(Correlations(None))

        for i in range(numero):
            self.correlationsManager.correlations[i].S1_pos = pickle.load(f)
            self.correlationsManager.correlations[i].S1_neg = pickle.load(f)
            self.correlationsManager.correlations[i].S2_pos = pickle.load(f)
            self.correlationsManager.correlations[i].S2_neg = pickle.load(f)
            self.correlationsManager.correlations[i].corr_active = pickle.load(f)
            self.correlationsManager.correlations[i].corr_type = pickle.load(f)
            self.correlationsManager.correlations[i].established = pickle.load(f)
            self.correlationsManager.correlations[i].i_reward = pickle.load(f)
            self.correlationsManager.correlations[i].i_reward_assigned = pickle.load(f)
        self.activeMot = pickle.load(f)
        self.activeCorr = pickle.load(f)
        self.corr_sensor = pickle.load(f)
        self.corr_type = pickle.load(f)
        self.iterations = pickle.load(f)
        action = pickle.load(f)
        seed = pickle.load(f)
        f.close()

        np.random.set_state(seed)

        return action


def main():
    instance = MDBCore()
    instance.run()


if __name__ == '__main__':
    main()

