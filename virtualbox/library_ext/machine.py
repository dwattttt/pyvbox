from __future__ import print_function
import time
import sys
import os
import shutil

import virtualbox
from virtualbox import library

"""
Add helper code to the default IMachine class.
"""


# Extend and fix IMachine :) 
class IMachine(library.IMachine):
    __doc__ = library.IMachine.__doc__

    def __str__(self):
        return self.name

    def remove(self, delete=True):
        """Unregister and optionally delete associated config

        Options:
            delete - remove all elements of this VM from the system

        Return the IMedia from unregistered VM 
        """
        if self.state >= library.MachineState.running:
            session = virtualbox.Session()
            self.lock_machine(session, LockType.shared)
            try:
                progress = session.console.power_down()
                progress.wait_for_completion(-1)
            except Exception as exc:
                print("Error powering off machine %s" % progress, 
                                            file=sys.stderr)
                pass
            session.unlock_machine()
            time.sleep(0.5) # TODO figure out how to ensure session is 
                            # really unlocked...

        settings_dir = os.path.dirname(self.settings_file_path)
        if delete:
            option = library.CleanupMode.detach_all_return_hard_disks_only
        else:
            option = library.CleanupMode.detach_all_return_none
        media = self.unregister(option)
        if delete:
            progress = self.delete_config(media)
            progress.wait_for_completion(-1)
            media = []
        
        # if delete - let's remove the settings folder too
        if delete:
            shutil.rmtree(settings_dir)

        return media

    def clone(self, snapshot_name_or_id=None, 
                    mode=library.CloneMode.machine_state, 
                    options=[library.CloneOptions.link], name=None, 
                    uuid=None, groups=[], basefolder='', register=True):
        """Clone this Machine 

        Options: 
            snapshot_name_or_id - value can be either ISnapshot, name, or id
            mode - set the CloneMode value
            options - define the CloneOptions options 
            name - define a name of the new VM
            uuid - set the uuid of the new VM
            groups - specify which groups the new VM will exist under
            basefolder - specify which folder to set the VM up under
            register - register this VM with the server
        
        Note: Default values create a linked clone from the current machine
              state

        Return a IMachine object for the newly cloned vm 
        """
        vbox = virtualbox.VirtualBox()

        if snapshot_name_or_id is not None:
            if snapshot_name_or_id in [str, unicode]:
                snapshot = self.find_snapshot(snapshot_name_or_id)
            else:
                snapshot = snapshot_name_or_id
            vm = snapshot.machine
        else:
            # linked clone can only be created from a snapshot... 
            # try grabbing the current_snapshot
            if library.CloneOptions.link in options:
                vm = self.current_snapshot.machine
            else:
                vm = self

        if name is None:
            name = "%s Clone" % vm.name

        # Build the settings file 
        create_flags = ''
        if uuid is not None:
            create_flags = "UUID=%s" % uuid
        primary_group = ''
        if groups:
            primary_group = groups[0]
        
        # Make sure this settings file does not already exist
        test_name = name
        for i in range(1, 1000):
            settings_file = vbox.compose_machine_filename(test_name,
                                    primary_group, create_flags, basefolder)
            if not os.path.exists(os.path.dirname(settings_file)):
                break
            test_name = "%s (%s)" % (name, i)
        name = test_name

        # Create the new machine and clone it!
        vm_clone = vbox.create_machine(settings_file, name, groups, '', 
                                        create_flags)
        progress = vm.clone_to(vm_clone, mode, options)
        progress.wait_for_completion(-1)

        if register:
            vbox.register_machine(vm_clone)
        return vm_clone

    # BUG: xidl describes this function as deleteConfig.  The interface seems
    #      to export plain "delete" instead... 
    def delete_config(self, media):
        if not isinstance(media, list):
            raise TypeError("media can only be an instance of type list")
        for a in media[:10]:
            if not isinstance(a, library.IMedium):
                raise TypeError(\
                        "array can only contain objects of type IMedium")
        progress = self._call("delete", in_p=[media])
        progress = library.IProgress(progress)
        return progress
    delete_config.__doc__ = library.IMachine.delete_config.__doc__

    # Add a helper to make locking and building a session simple
    def create_session(self, lock_type=library.LockType.shared,
                   session=None):
        """Lock this machine
        
        Arguments:
            lock_type - see IMachine.lock_machine for details
            session - optionally define a session object to lock this machine 
                      against.  If not defined, a new ISession object is 
                      created to lock against
        
        return an ISession object
        """ 
        if session is None:
            session = library.ISession()
        # NOTE: The following hack handles the issue of unknown machine state.
        #       This occurs most frequently when a machine is powered off and
        #       in spite waiting for the completion event to end, the state of
        #       machine still raises the following Error:
        #          virtualbox.library.VBoxErrorVmError: 0x80bb0003 (Failed to \
        #          get a console object from the direct session (Unknown \
        #          Status 0x80BB0002))
        for i in range(10):
            try:
                self.lock_machine(session, lock_type)
            except Exception as exc:
                time.sleep(1)
                continue
            else:
                break
        else:
            raise Exception("Failed to create clone - %s" % exc)
        return session

    # Simplify the launch_vm_process. Build a ISession if it has not been 
    # defined... 
    def launch_vm_process(self, session=None, type_p='gui', environment=''):
        if session is None:
            local_session = library.ISession()
        else:
            local_session = session
        p = super(IMachine, self).launch_vm_process(local_session, 
                                                    type_p, environment)
        if session is None:
            p.wait_for_completion(-1)
            local_session.unlock_machine()
        return p
    launch_vm_process.__doc__ = library.IMachine.launch_vm_process.__doc__



