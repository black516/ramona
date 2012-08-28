import sys, os, time, logging, shlex, signal
from ..config import config
#

L = logging.getLogger("subproc")

#

class program(object):

	DEFAULTS = {
		'command': None,
		'launchtime': 5,
	}


	class state_enum:
		'''Enum'''
		STOPPED = 0
		STARTING = 10
		RUNNING = 20
		STOPPING = 30
		FATAL = 200

		labels = {
			STOPPED: 'STOPPED',
			STARTING: 'STARTING',
			RUNNING: 'RUNNING',
			STOPPING: 'STOPPING',
			FATAL: 'FATAL',
		}


	def __init__(self, config_section):
		_, self.ident = config_section.split(':', 2)
		self.state = program.state_enum.STOPPED
		self.pid = None

		self.launch_cnt = 0
		self.start_time = None
		self.term_time = None

		# Build configuration
		self.config = self.DEFAULTS.copy()
		self.config.update(config.items(config_section))

		cmd = self.config.get('command')
		if cmd is None:
			L.fatal("Program {0} doesn't specify command - don't know how to launch it".format(self.ident))
			sys.exit(2)

		self.cmdline = shlex.split(cmd)


	def __repr__(self):
		return "<{0} {1} state={2} pid={3}>".format(self.__class__.__name__, self.ident, program.state_enum.labels[self.state],self.pid if self.pid is not None else '?')


	def start(self):
		'''Transition to state STARTING'''
		assert self.state == program.state_enum.STOPPED

		L.debug("{0} -> STARTING".format(self))

		self.pid = os.spawnvp(os.P_NOWAIT, self.cmdline[0], self.cmdline) #TODO: self.cmdline[0] can be substituted by self.ident or any arbitrary string
		self.state = program.state_enum.STARTING
		self.start_time = time.time()
		self.term_time = None
		self.launch_cnt += 1


	def stop(self):
		'''Transition to state STOPPING'''
		assert self.pid is not None

		L.debug("{0} -> STOPPING".format(self))
		os.kill(self.pid, signal.SIGTERM) #TODO: Configure signals that are used for process stop
		self.state = program.state_enum.STOPPING


	def on_terminate(self, status):
		self.term_time = time.time()
		self.pid = None

		if self.state == program.state_enum.STARTING:
			L.warning("{0} exited too quickly (-> FATAL)".format(self))
			self.state = program.state_enum.FATAL

		elif self.state == program.state_enum.STOPPING:
			L.debug("{0} -> STOPPED".format(self))
			self.state = program.state_enum.STOPPED

		else:
			L.warning("{0} exited unexpectedly (-> FATAL)".format(self))
			self.state = program.state_enum.FATAL


	def on_tick(self, now):
		# Switch starting programs into running state
		if self.state == program.state_enum.STARTING:
			if now - self.start_time >= self.config['launchtime']:
				L.debug("{0} -> RUNNING".format(self))
				self.state = program.state_enum.RUNNING

###

class program_roaster(object):

	def __init__(self):
		self.roaster = []
		for config_section in config.sections():
			if config_section.find('program:') != 0: continue
			sp = program(config_section)
			self.roaster.append(sp)


	def start_program(self):
		# Start processes that are STOPPED
		#TODO: Switch to allow starting state.FATAL programs too
		for p in self.roaster:
			if p.state not in (program.state_enum.STOPPED,): continue
			p.start()


	def stop_program(self):
		# Stop processes that are RUNNING and STARTING
		for p in self.roaster:
			if p.state not in (program.state_enum.RUNNING, program.state_enum.STARTING): continue
			p.stop()



	def on_terminate_program(self, pid, status):
		for p in self.roaster:
			if pid != p.pid: continue
			return p.on_terminate(status)
		else:
			L.warning("Unknown program died (pid={0}, status={1})".format(pid, status))


	def on_periodic_program_check(self):
		now = time.time()
		for p in self.roaster:
			p.on_tick(now)
